"""Restart-safe autonomous work queue and continuation worker for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
from typing import Callable

from .event_continuation import ContinuationEvent, EventDrivenContinuation, EventType


@dataclass(frozen=True)
class WorkItem:
    job_id: str
    event_type: str
    subject: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_until: str | None
    status: str
    last_error: str | None


class DurableWorkQueue:
    """SQLite queue with leases, retries, recovery, idempotency and dead-lettering."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS work_queue (
              job_id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              subject TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 5,
              available_at TEXT NOT NULL,
              lease_owner TEXT,
              lease_until TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_work_claim
              ON work_queue(status, available_at, lease_until, created_at);
            """)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat()

    def enqueue(self, job_id: str, event_type: str, subject: str, payload: dict[str, object] | None = None, max_attempts: int = 5) -> bool:
        if not job_id.strip() or not event_type.strip() or not subject.strip():
            raise ValueError("job_id, event_type and subject are required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        now = self._iso(self._now())
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO work_queue(job_id,event_type,subject,payload_json,max_attempts,available_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (job_id, event_type, subject, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), max_attempts, now, now, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def recover_expired_leases(self) -> int:
        now = self._iso(self._now())
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE work_queue SET status='pending', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE status='leased' AND lease_until<=?",
                (now, now),
            )
            return cur.rowcount

    def claim(self, worker_id: str, lease_seconds: int = 60) -> WorkItem | None:
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("valid worker_id and lease_seconds are required")
        self.recover_expired_leases()
        now_dt = self._now()
        now = self._iso(now_dt)
        lease_until = self._iso(now_dt + timedelta(seconds=lease_seconds))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT job_id FROM work_queue WHERE status='pending' AND available_at<=? ORDER BY created_at, job_id LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            cur = conn.execute(
                "UPDATE work_queue SET status='leased', lease_owner=?, lease_until=?, attempts=attempts+1, updated_at=? WHERE job_id=? AND status='pending'",
                (worker_id, lease_until, now, row['job_id']),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            result = conn.execute("SELECT * FROM work_queue WHERE job_id=?", (row['job_id'],)).fetchone()
            conn.commit()
        return self._row(result)

    def complete(self, job_id: str, worker_id: str) -> bool:
        now = self._iso(self._now())
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE work_queue SET status='completed', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE job_id=? AND status='leased' AND lease_owner=?",
                (now, job_id, worker_id),
            )
            return cur.rowcount == 1

    def fail(self, job_id: str, worker_id: str, error: str, backoff_seconds: int = 0) -> str:
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        now_dt = self._now()
        now = self._iso(now_dt)
        with self._connect() as conn:
            row = conn.execute("SELECT attempts,max_attempts FROM work_queue WHERE job_id=? AND status='leased' AND lease_owner=?", (job_id, worker_id)).fetchone()
            if row is None:
                return "not-owned"
            status = "dead" if row["attempts"] >= row["max_attempts"] else "pending"
            available = self._iso(now_dt + timedelta(seconds=backoff_seconds))
            conn.execute(
                "UPDATE work_queue SET status=?, available_at=?, lease_owner=NULL, lease_until=NULL, last_error=?, updated_at=? WHERE job_id=?",
                (status, available, error, now, job_id),
            )
            return status

    def get(self, job_id: str) -> WorkItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM work_queue WHERE job_id=?", (job_id,)).fetchone()
        return None if row is None else self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> WorkItem:
        return WorkItem(row["job_id"], row["event_type"], row["subject"], json.loads(row["payload_json"]), row["attempts"], row["max_attempts"], row["lease_owner"], row["lease_until"], row["status"], row["last_error"])


class DurableContinuationWorker:
    """Consumes durable events and delegates each one to the guarded continuation engine."""

    def __init__(self, queue: DurableWorkQueue, engine: EventDrivenContinuation, worker_id: str, backoff: Callable[[int], int] | None = None):
        self.queue = queue
        self.engine = engine
        self.worker_id = worker_id
        self.backoff = backoff or (lambda attempts: min(300, 2 ** max(0, attempts - 1)))

    def run_once(self) -> str:
        item = self.queue.claim(self.worker_id)
        if item is None:
            return "idle"
        try:
            event = ContinuationEvent(item.job_id, EventType(item.event_type), item.subject, item.payload)
            decision = self.engine.handle(event)
            if decision.status == "failed":
                return self.queue.fail(item.job_id, self.worker_id, decision.reason, self.backoff(item.attempts))
            if not self.queue.complete(item.job_id, self.worker_id):
                raise RuntimeError("lost work lease before completion")
            return decision.status
        except Exception as exc:
            return self.queue.fail(item.job_id, self.worker_id, f"{type(exc).__name__}: {exc}", self.backoff(item.attempts))
