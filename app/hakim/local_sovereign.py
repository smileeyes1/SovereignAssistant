"""Local-first sovereign runtime for HAKIM Ω.

This module is deliberately standard-library only. It provides a durable local
state store, idempotent work queue, evidence ledger, immutable/promotion-gated
checkpoints, verified backups, a loopback-only OpenAI-compatible model adapter,
and a small guarded local tool surface. No cloud provider, account, external
memory service, or network connection is required for the core runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid
import zipfile


FINAL_STATUSES = {"PASS", "CONDITIONAL_PASS", "NOT_PROVEN", "FAIL", "NO_GO", "BLOCKED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class QueueItem:
    job_id: str
    idempotency_key: str
    goal: str
    payload: dict[str, Any]
    priority: int
    status: str
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_until: str | None
    last_error: str | None


class LocalSovereignStore:
    """SQLite-owned truth: state, queue, evidence, checkpoints, and audit."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv_state(
                  key TEXT PRIMARY KEY,
                  value_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_queue(
                  job_id TEXT PRIMARY KEY,
                  idempotency_key TEXT NOT NULL UNIQUE,
                  goal TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  priority INTEGER NOT NULL DEFAULT 50,
                  status TEXT NOT NULL DEFAULT 'pending',
                  attempts INTEGER NOT NULL DEFAULT 0,
                  max_attempts INTEGER NOT NULL DEFAULT 5,
                  available_at TEXT NOT NULL,
                  lease_owner TEXT,
                  lease_until TEXT,
                  last_error TEXT,
                  result_json TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_local_work_claim
                  ON work_queue(status, priority, available_at, created_at);
                CREATE TABLE IF NOT EXISTS evidence_ledger(
                  evidence_id TEXT PRIMARY KEY,
                  claim TEXT NOT NULL,
                  source TEXT NOT NULL,
                  observation TEXT NOT NULL,
                  scope TEXT NOT NULL,
                  status TEXT NOT NULL,
                  artifact_hash TEXT,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints(
                  checkpoint_id TEXT PRIMARY KEY,
                  parent_id TEXT,
                  state_json TEXT NOT NULL,
                  state_hash TEXT NOT NULL,
                  verified INTEGER NOT NULL DEFAULT 0,
                  promoted INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(parent_id) REFERENCES checkpoints(checkpoint_id)
                );
                CREATE TABLE IF NOT EXISTS audit_log(
                  seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_type TEXT NOT NULL,
                  subject TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )

    def set(self, key: str, value: Any) -> None:
        if not key.strip():
            raise ValueError("state key is required")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO kv_state(key,value_json,updated_at) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
                (key, _stable_json(value), now),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT value_json FROM kv_state WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def audit(self, event_type: str, subject: str, payload: dict[str, Any] | None = None) -> None:
        if not event_type.strip() or not subject.strip():
            raise ValueError("event_type and subject are required")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log(event_type,subject,payload_json,created_at) VALUES(?,?,?,?)",
                (event_type, subject, _stable_json(payload or {}), _now()),
            )

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "seq": r["seq"],
                "event_type": r["event_type"],
                "subject": r["subject"],
                "payload": json.loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def enqueue_goal(
        self,
        goal: str,
        *,
        payload: dict[str, Any] | None = None,
        priority: int = 50,
        max_attempts: int = 5,
        idempotency_key: str | None = None,
    ) -> str:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required")
        if not 0 <= priority <= 100:
            raise ValueError("priority must be in [0,100]")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        payload = payload or {}
        idem = idempotency_key or _sha256_bytes(_stable_json({"goal": goal, "payload": payload}).encode())
        job_id = str(uuid.uuid4())
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO work_queue(job_id,idempotency_key,goal,payload_json,priority,max_attempts,available_at,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (job_id, idem, goal, _stable_json(payload), priority, max_attempts, now, now, now),
                )
        except sqlite3.IntegrityError:
            with self._connect() as conn:
                row = conn.execute("SELECT job_id FROM work_queue WHERE idempotency_key=?", (idem,)).fetchone()
            if row is None:
                raise
            return str(row["job_id"])
        self.audit("goal.enqueued", job_id, {"goal": goal, "priority": priority, "idempotency_key": idem})
        return job_id

    def recover_expired_leases(self) -> int:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE work_queue SET status='pending',lease_owner=NULL,lease_until=NULL,updated_at=?
                   WHERE status='leased' AND lease_until<=?""",
                (now, now),
            )
            count = cur.rowcount
        if count:
            self.audit("queue.recovered", "expired-leases", {"count": count})
        return count

    def claim_next(self, worker_id: str, *, lease_seconds: int = 120) -> QueueItem | None:
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("valid worker_id and lease_seconds required")
        self.recover_expired_leases()
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT job_id FROM work_queue
                   WHERE status='pending' AND available_at<=?
                   ORDER BY priority DESC, created_at, job_id LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            cur = conn.execute(
                """UPDATE work_queue SET status='leased',lease_owner=?,lease_until=?,attempts=attempts+1,updated_at=?
                   WHERE job_id=? AND status='pending'""",
                (worker_id, lease_until, now, row["job_id"]),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            full = conn.execute("SELECT * FROM work_queue WHERE job_id=?", (row["job_id"],)).fetchone()
            conn.commit()
        return self._queue_item(full)

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> bool:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE work_queue SET status='completed',lease_owner=NULL,lease_until=NULL,result_json=?,updated_at=?
                   WHERE job_id=? AND status='leased' AND lease_owner=?""",
                (_stable_json(result), now, job_id, worker_id),
            )
            ok = cur.rowcount == 1
        if ok:
            self.audit("goal.completed", job_id, result)
        return ok

    def fail(self, job_id: str, worker_id: str, error: str, *, backoff_seconds: int = 0) -> str:
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempts,max_attempts FROM work_queue WHERE job_id=? AND status='leased' AND lease_owner=?",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                return "not-owned"
            status = "dead" if row["attempts"] >= row["max_attempts"] else "pending"
            available = (now_dt + timedelta(seconds=backoff_seconds)).isoformat()
            conn.execute(
                """UPDATE work_queue SET status=?,available_at=?,lease_owner=NULL,lease_until=NULL,last_error=?,updated_at=?
                   WHERE job_id=?""",
                (status, available, error, now, job_id),
            )
        self.audit("goal.failed", job_id, {"status": status, "error": error})
        return status

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM work_queue WHERE job_id=?", (job_id,)).fetchone()
        if r is None:
            return None
        return {
            "job_id": r["job_id"], "goal": r["goal"], "status": r["status"],
            "attempts": r["attempts"], "max_attempts": r["max_attempts"],
            "last_error": r["last_error"],
            "result": None if r["result_json"] is None else json.loads(r["result_json"]),
        }

    def queue_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status,COUNT(*) n FROM work_queue GROUP BY status").fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def add_evidence(
        self, claim: str, source: str, observation: str, scope: str,
        status: str, artifact_hash: str | None = None,
    ) -> str:
        if status not in FINAL_STATUSES:
            raise ValueError("invalid evidence status")
        eid = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO evidence_ledger VALUES(?,?,?,?,?,?,?,?)",
                (eid, claim, source, observation, scope, status, artifact_hash, _now()),
            )
        return eid

    def create_checkpoint(self, state: dict[str, Any]) -> str:
        parent = self.last_verified_checkpoint_id()
        payload = _stable_json(state)
        cid = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO checkpoints(checkpoint_id,parent_id,state_json,state_hash,created_at) VALUES(?,?,?,?,?)",
                (cid, parent, payload, _sha256_bytes(payload.encode()), _now()),
            )
        self.audit("checkpoint.candidate", cid, {"parent": parent})
        return cid

    def verify_checkpoint(self, checkpoint_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute("UPDATE checkpoints SET verified=1 WHERE checkpoint_id=?", (checkpoint_id,))
            if cur.rowcount != 1:
                raise KeyError(checkpoint_id)
        self.audit("checkpoint.verified", checkpoint_id)

    def promote_checkpoint(self, checkpoint_id: str) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT verified FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone()
            if row is None:
                conn.rollback(); raise KeyError(checkpoint_id)
            if not bool(row["verified"]):
                conn.rollback(); raise RuntimeError("cannot promote unverified checkpoint")
            conn.execute("UPDATE checkpoints SET promoted=0 WHERE promoted=1")
            conn.execute("UPDATE checkpoints SET promoted=1 WHERE checkpoint_id=?", (checkpoint_id,))
            conn.commit()
        self.audit("checkpoint.promoted", checkpoint_id)

    def last_verified_checkpoint_id(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE promoted=1 AND verified=1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else str(row["checkpoint_id"])

    def last_verified_checkpoint(self) -> dict[str, Any] | None:
        cid = self.last_verified_checkpoint_id()
        if cid is None:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT state_json FROM checkpoints WHERE checkpoint_id=?", (cid,)).fetchone()
        return json.loads(row["state_json"])

    @staticmethod
    def _queue_item(row: sqlite3.Row) -> QueueItem:
        return QueueItem(
            str(row["job_id"]), str(row["idempotency_key"]), str(row["goal"]),
            json.loads(row["payload_json"]), int(row["priority"]), str(row["status"]),
            int(row["attempts"]), int(row["max_attempts"]), row["lease_owner"],
            row["lease_until"], row["last_error"],
        )


class VerifiedBackupManager:
    """Create and verify portable backups without trusting the live DB copy."""

    def __init__(self, store: LocalSovereignStore, backup_dir: str | Path):
        self.store = store
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create(self, *, label: str = "checkpoint", extra_files: Iterable[str | Path] = ()) -> Path:
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_") or "checkpoint"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        final = self.backup_dir / f"omega-{safe_label}-{stamp}.zip"
        with tempfile.TemporaryDirectory(dir=self.backup_dir) as td:
            td_path = Path(td)
            db_copy = td_path / "sovereign.db"
            with sqlite3.connect(self.store.path) as src, sqlite3.connect(db_copy) as dst:
                src.backup(dst)
            members: dict[str, str] = {"sovereign.db": sha256_file(db_copy)}
            staged: list[tuple[Path, str]] = [(db_copy, "sovereign.db")]
            for raw in extra_files:
                p = Path(raw)
                if not p.exists() or not p.is_file():
                    raise FileNotFoundError(p)
                arc = f"extras/{p.name}"
                if arc in members:
                    raise ValueError(f"duplicate backup member: {arc}")
                members[arc] = sha256_file(p)
                staged.append((p, arc))
            manifest = {
                "format": 1,
                "created_at": _now(),
                "members": members,
                "last_verified_checkpoint": self.store.last_verified_checkpoint_id(),
            }
            manifest_path = td_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_zip = td_path / "backup.zip"
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(manifest_path, "manifest.json")
                for src, arc in staged:
                    z.write(src, arc)
            os.replace(tmp_zip, final)
        if not self.verify(final):
            final.unlink(missing_ok=True)
            raise RuntimeError("backup verification failed")
        self.store.audit("backup.created", final.name, {"sha256": sha256_file(final)})
        return final

    @staticmethod
    def verify(path: str | Path) -> bool:
        p = Path(path)
        try:
            with zipfile.ZipFile(p, "r") as z:
                if z.testzip() is not None:
                    return False
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
                members = manifest.get("members", {})
                if not isinstance(members, dict) or "sovereign.db" not in members:
                    return False
                for name, expected in members.items():
                    if _sha256_bytes(z.read(name)) != expected:
                        return False
            return True
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            return False

    @staticmethod
    def restore(path: str | Path, target_dir: str | Path, *, overwrite: bool = False) -> Path:
        if not VerifiedBackupManager.verify(path):
            raise ValueError("backup is not valid")
        target = Path(target_dir)
        if target.exists() and any(target.iterdir()) and not overwrite:
            raise FileExistsError("target directory is not empty")
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "r") as z:
            db_bytes = z.read("sovereign.db")
        restored = target / "sovereign.db"
        tmp = target / ".sovereign.db.tmp"
        tmp.write_bytes(db_bytes)
        os.replace(tmp, restored)
        return restored


class LocalModelClient:
    """Loopback-only OpenAI-compatible local model client by default."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://127.0.0.1:8080/v1",
        allow_remote: bool = False,
        opener=None,
        timeout: int = 180,
    ):
        if not model.strip():
            raise ValueError("model is required")
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if not allow_remote and host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("remote model endpoints are disabled in sovereign-local mode")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must use http or https")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._opener = opener or urlopen
        self.timeout = timeout

    def health(self) -> bool:
        for suffix in ("/models",):
            try:
                req = Request(self.base_url + suffix, headers={"Accept": "application/json"})
                response = self._opener(req, timeout=min(10, self.timeout))
                code = getattr(response, "status", 200)
                if 200 <= int(code) < 300:
                    return True
            except Exception:
                pass
        return False

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 2048, temperature: float = 0.1) -> str:
        body = json.dumps(
            {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            ensure_ascii=False,
        ).encode("utf-8")
        req = Request(
            self.base_url + "/chat/completions",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = self._opener(req, timeout=self.timeout)
        data = json.loads(response.read().decode("utf-8"))
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("local model response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ValueError("local model response has no message content")
        return content


class GuardedWorkspace:
    """Small reversible tool surface confined to one owned workspace."""

    def __init__(self, root: str | Path, store: LocalSovereignStore, *, allowed_commands: Iterable[str] = ("python", "python3", "pytest")):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.allowed_commands = frozenset(allowed_commands)
        self.undo_dir = self.root / ".omega" / "undo"
        self.undo_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, relative: str) -> Path:
        p = (self.root / relative).resolve()
        try:
            p.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes sovereign workspace") from exc
        return p

    def list_dir(self, relative: str = ".") -> list[str]:
        p = self._path(relative)
        if not p.is_dir():
            raise NotADirectoryError(relative)
        return sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir() if x.name != ".omega")

    def read_text(self, relative: str, *, max_chars: int = 200_000) -> str:
        p = self._path(relative)
        text = p.read_text(encoding="utf-8")
        if len(text) > max_chars:
            raise ValueError("file exceeds read budget")
        return text

    def search_text(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        q = query.casefold().strip()
        if not q:
            raise ValueError("query is required")
        hits: list[dict[str, Any]] = []
        for p in sorted(self.root.rglob("*")):
            if len(hits) >= limit:
                break
            if not p.is_file() or ".omega" in p.parts or p.stat().st_size > 1_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            idx = text.casefold().find(q)
            if idx >= 0:
                hits.append({"path": str(p.relative_to(self.root)), "excerpt": text[max(0, idx-120):idx+len(query)+240]})
        return hits

    def write_text(self, relative: str, content: str) -> dict[str, Any]:
        p = self._path(relative)
        p.parent.mkdir(parents=True, exist_ok=True)
        prior_hash = sha256_file(p) if p.exists() and p.is_file() else None
        if p.exists():
            backup_name = f"{uuid.uuid4()}-{p.name}"
            shutil.copy2(p, self.undo_dir / backup_name)
        tmp = p.with_name("." + p.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, p)
        new_hash = sha256_file(p)
        self.store.audit("file.write", str(p.relative_to(self.root)), {"prior_hash": prior_hash, "new_hash": new_hash})
        return {"path": str(p.relative_to(self.root)), "sha256": new_hash, "prior_sha256": prior_hash}

    def mkdir(self, relative: str) -> str:
        p = self._path(relative)
        p.mkdir(parents=True, exist_ok=True)
        self.store.audit("dir.mkdir", str(p.relative_to(self.root)))
        return str(p.relative_to(self.root))

    def hash_file(self, relative: str) -> str:
        return sha256_file(self._path(relative))

    def run_process(self, argv: list[str], *, timeout: int = 120) -> dict[str, Any]:
        if not argv or argv[0] not in self.allowed_commands:
            raise PermissionError("command is not in the local reversible allowlist")
        if any("\x00" in arg for arg in argv):
            raise ValueError("invalid command argument")
        proc = subprocess.run(argv, cwd=self.root, text=True, capture_output=True, timeout=timeout, shell=False)
        result = {"returncode": proc.returncode, "stdout": proc.stdout[-20000:], "stderr": proc.stderr[-20000:]}
        self.store.audit("process.run", argv[0], {"argv": argv, "returncode": proc.returncode})
        return result

    def dispatch(self, tool: str, args: dict[str, Any]) -> Any:
        if tool == "list_dir": return self.list_dir(str(args.get("path", ".")))
        if tool == "read_text": return self.read_text(str(args["path"]))
        if tool == "search_text": return self.search_text(str(args["query"]), limit=int(args.get("limit", 20)))
        if tool == "write_text": return self.write_text(str(args["path"]), str(args["content"]))
        if tool == "mkdir": return self.mkdir(str(args["path"]))
        if tool == "sha256": return self.hash_file(str(args["path"]))
        if tool == "run_process":
            argv = args.get("argv")
            if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
                raise ValueError("argv must be a list of strings")
            return self.run_process(argv, timeout=int(args.get("timeout", 120)))
        raise KeyError(f"unknown local tool: {tool}")


class LocalAgentLoop:
    """A bounded autonomous loop whose model and tools are both local."""

    SYSTEM = """You are HAKIM Ω local sovereign agent. You have no cloud memory and no external authority.
Work only toward the user's stated goal. Preserve verified success. Prefer the smallest safe reversible action.
Return exactly one JSON object per turn, no Markdown. Either:
{"action":"tool","tool":"list_dir|read_text|search_text|write_text|mkdir|sha256|run_process","args":{...},"reason":"..."}
or {"action":"final","status":"PASS|CONDITIONAL_PASS|NOT_PROVEN|FAIL|NO_GO|BLOCKED","message":"..."}.
Never request shell execution through write_text. Never invent tool results. If a consequential/irreversible action would be required, return BLOCKED and explain the required human authority."""

    def __init__(self, store: LocalSovereignStore, workspace: GuardedWorkspace, model: LocalModelClient, *, worker_id: str = "omega-local-1"):
        self.store = store
        self.workspace = workspace
        self.model = model
        self.worker_id = worker_id

    @staticmethod
    def _json_object(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("model output is not JSON")
        obj = json.loads(cleaned[start:end+1])
        if not isinstance(obj, dict):
            raise ValueError("model output must be an object")
        return obj

    def run_goal(self, goal: str, *, max_steps: int = 12) -> dict[str, Any]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": goal},
        ]
        for step in range(1, max_steps + 1):
            raw = self.model.chat(messages)
            decision = self._json_object(raw)
            action = decision.get("action")
            if action == "final":
                status = str(decision.get("status", "NOT_PROVEN"))
                if status not in FINAL_STATUSES:
                    raise ValueError("invalid final status")
                result = {"status": status, "message": str(decision.get("message", "")), "steps": step}
                self.store.audit("agent.final", goal[:120], result)
                return result
            if action != "tool":
                raise ValueError("action must be tool or final")
            tool = str(decision.get("tool", ""))
            args = decision.get("args", {})
            if not isinstance(args, dict):
                raise ValueError("tool args must be an object")
            try:
                output = self.workspace.dispatch(tool, args)
                tool_result = {"ok": True, "tool": tool, "result": output}
            except Exception as exc:
                tool_result = {"ok": False, "tool": tool, "error": f"{type(exc).__name__}: {exc}"}
            self.store.audit("agent.tool", tool, {"step": step, **tool_result})
            messages.append({"role": "assistant", "content": _stable_json(decision)})
            messages.append({"role": "user", "content": "TOOL_RESULT " + _stable_json(tool_result)})
        result = {"status": "NOT_PROVEN", "message": "bounded local loop exhausted before a qualified final state", "steps": max_steps}
        self.store.audit("agent.exhausted", goal[:120], result)
        return result

    def process_once(self, *, max_steps: int = 12) -> str:
        item = self.store.claim_next(self.worker_id)
        if item is None:
            return "idle"
        try:
            result = self.run_goal(item.goal, max_steps=max_steps)
            if result["status"] in {"FAIL", "NO_GO"}:
                return self.store.fail(item.job_id, self.worker_id, result["message"], backoff_seconds=min(300, 2 ** max(0, item.attempts - 1)))
            if not self.store.complete(item.job_id, self.worker_id, result):
                raise RuntimeError("lost local work lease")
            return str(result["status"])
        except Exception as exc:
            return self.store.fail(item.job_id, self.worker_id, f"{type(exc).__name__}: {exc}", backoff_seconds=min(300, 2 ** max(0, item.attempts - 1)))


@dataclass(frozen=True)
class LocalSovereignConfig:
    root: Path
    model: str = ""
    model_base_url: str = "http://127.0.0.1:8080/v1"

    @property
    def omega_dir(self) -> Path: return self.root / ".omega"
    @property
    def db_path(self) -> Path: return self.omega_dir / "sovereign.db"
    @property
    def backup_dir(self) -> Path: return self.omega_dir / "backups"


class LocalSovereignRuntime:
    def __init__(self, config: LocalSovereignConfig):
        self.config = config
        self.config.root.mkdir(parents=True, exist_ok=True)
        self.store = LocalSovereignStore(config.db_path)
        self.workspace = GuardedWorkspace(config.root, self.store)
        self.backups = VerifiedBackupManager(self.store, config.backup_dir)
        self.model = LocalModelClient(config.model, base_url=config.model_base_url) if config.model.strip() else None

    def doctor(self) -> dict[str, Any]:
        db_ok = self.config.db_path.exists() and os.access(self.config.db_path.parent, os.W_OK)
        model_configured = self.model is not None
        model_healthy = self.model.health() if self.model is not None else False
        lkg = self.store.last_verified_checkpoint_id()
        return {
            "runtime": "PASS" if db_ok else "FAIL",
            "state_db": "PASS" if db_ok else "FAIL",
            "model": "PASS" if model_healthy else ("NOT_PROVEN" if model_configured else "NOT_CONFIGURED"),
            "offline_core": "PASS" if db_ok else "FAIL",
            "last_verified_checkpoint": lkg,
            "queue": self.store.queue_counts(),
        }
