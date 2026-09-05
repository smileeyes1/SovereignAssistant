"""Durable end-user task and artifact contract for HAKIM Ω."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


TERMINAL_STATUSES = frozenset({"completed", "failed"})
ACTIVE_STATUSES = frozenset({"queued", "running"})


@dataclass(frozen=True)
class EndUserTask:
    task_id: str
    prompt: str
    status: str
    idempotency_key: str | None
    result: dict[str, object] | None
    error: str | None
    artifact_name: str | None
    artifact_media_type: str | None
    verified: bool
    created_at: str
    updated_at: str

    def public_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "status": self.status,
            "verified": self.verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            value["result"] = self.result
        if self.error:
            value["error"] = self.error
        if self.artifact_name:
            value["artifact"] = {
                "name": self.artifact_name,
                "media_type": self.artifact_media_type or "application/octet-stream",
                "url": f"/tasks/{self.task_id}/artifact",
            }
        return value


class EndUserTaskStore:
    """SQLite-backed task state sharing the runtime database without hidden SaaS dependencies."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS end_user_tasks (
                    task_id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    result_json TEXT,
                    error TEXT,
                    artifact_name TEXT,
                    artifact_media_type TEXT,
                    verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_end_user_tasks_status
                    ON end_user_tasks(status, created_at);
                """
            )

    def submit(self, prompt: str, *, idempotency_key: str | None = None) -> tuple[EndUserTask, bool]:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt is required")
        if len(prompt) > 20_000:
            raise ValueError("prompt is too large")
        idem = None if idempotency_key is None else idempotency_key.strip()
        if idem == "":
            idem = None
        if idem is not None and len(idem) > 200:
            raise ValueError("idempotency key is too large")
        if idem is not None:
            existing = self.get_by_idempotency_key(idem)
            if existing is not None:
                return existing, False
        task_id = uuid.uuid4().hex
        now = self._now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO end_user_tasks(
                        task_id,prompt,status,idempotency_key,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?)""",
                    (task_id, prompt, "queued", idem, now, now),
                )
        except sqlite3.IntegrityError:
            if idem is not None:
                existing = self.get_by_idempotency_key(idem)
                if existing is not None:
                    return existing, False
            raise
        task = self.get(task_id)
        assert task is not None
        return task, True

    def get(self, task_id: str) -> EndUserTask | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM end_user_tasks WHERE task_id=?", (task_id,)).fetchone()
        return None if row is None else self._row(row)

    def get_by_idempotency_key(self, key: str) -> EndUserTask | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM end_user_tasks WHERE idempotency_key=?", (key,)).fetchone()
        return None if row is None else self._row(row)

    def unfinished(self, limit: int = 100) -> list[EndUserTask]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM end_user_tasks WHERE status IN ('queued','running') ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def mark_running(self, task_id: str) -> EndUserTask:
        self._transition(task_id, "running")
        task = self.get(task_id)
        assert task is not None
        return task

    def complete(
        self,
        task_id: str,
        *,
        result: dict[str, object] | None = None,
        artifact_name: str | None = None,
        artifact_media_type: str | None = None,
        verified: bool = False,
    ) -> EndUserTask:
        if artifact_name is not None:
            artifact_name = Path(artifact_name).name
            if not artifact_name:
                raise ValueError("artifact name is invalid")
        now = self._now()
        payload = None if result is None else json.dumps(result, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE end_user_tasks SET status='completed', result_json=?, error=NULL,
                   artifact_name=?, artifact_media_type=?, verified=?, updated_at=? WHERE task_id=?""",
                (payload, artifact_name, artifact_media_type, int(verified), now, task_id),
            )
            if cur.rowcount != 1:
                raise KeyError(task_id)
        task = self.get(task_id)
        assert task is not None
        return task

    def fail(self, task_id: str, error: str) -> EndUserTask:
        error = error.strip() or "task failed"
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE end_user_tasks SET status='failed', error=?, verified=0, updated_at=? WHERE task_id=?""",
                (error[:4000], self._now(), task_id),
            )
            if cur.rowcount != 1:
                raise KeyError(task_id)
        task = self.get(task_id)
        assert task is not None
        return task

    def _transition(self, task_id: str, status: str) -> None:
        if status not in {"queued", "running"}:
            raise ValueError("invalid active status")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE end_user_tasks SET status=?, updated_at=? WHERE task_id=? AND status NOT IN ('completed','failed')",
                (status, self._now(), task_id),
            )
            if cur.rowcount != 1:
                if self.get(task_id) is None:
                    raise KeyError(task_id)
                raise RuntimeError("cannot transition terminal task")

    @staticmethod
    def _row(row: sqlite3.Row) -> EndUserTask:
        return EndUserTask(
            task_id=row["task_id"],
            prompt=row["prompt"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            result=None if row["result_json"] is None else json.loads(row["result_json"]),
            error=row["error"],
            artifact_name=row["artifact_name"],
            artifact_media_type=row["artifact_media_type"],
            verified=bool(row["verified"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
