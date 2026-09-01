"""Durable canonical state and event log for Ω APEX.

SQLite is used as the first sovereign persistence backend because it is local,
portable, transactional, dependency-free, and easy to replace later behind the
same repository boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    event_type: str
    subject: str
    payload: dict[str, object]
    created_at: str
    processed: bool


class DurableStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_events_pending
                    ON events(processed, created_at);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_state(self, key: str, value: object) -> None:
        if not key.strip():
            raise ValueError("state key is required")
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO state(key, value_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value_json=excluded.value_json,
                     updated_at=excluded.updated_at""",
                (key, payload, self._now()),
            )

    def get_state(self, key: str, default: object = None) -> object:
        with self._connect() as conn:
            row = conn.execute("SELECT value_json FROM state WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def append_event(self, event_id: str, event_type: str, subject: str, payload: dict[str, object] | None = None) -> bool:
        if not event_id.strip():
            raise ValueError("event_id is required")
        if not event_type.strip():
            raise ValueError("event_type is required")
        if not subject.strip():
            raise ValueError("subject is required")
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO events(event_id,event_type,subject,payload_json,created_at) VALUES (?,?,?,?,?)",
                    (event_id, event_type, subject, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), self._now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def pending_events(self, limit: int = 100) -> list[StoredEvent]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE processed=0 ORDER BY created_at, event_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def mark_processed(self, event_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE events SET processed=1 WHERE event_id=? AND processed=0", (event_id,))
            return cur.rowcount == 1

    def all_events(self) -> Iterable[StoredEvent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY created_at, event_id").fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> StoredEvent:
        return StoredEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            subject=row["subject"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            processed=bool(row["processed"]),
        )


class ResumeCursor:
    """Minimal durable resume contract for crash/restart continuity."""

    KEY = "omega.resume"

    def __init__(self, store: DurableStateStore):
        self.store = store

    def save(self, *, release: str, task: str, checkpoint: str, next_action: str) -> None:
        self.store.set_state(
            self.KEY,
            {
                "release": release,
                "task": task,
                "checkpoint": checkpoint,
                "next_action": next_action,
            },
        )

    def load(self) -> dict[str, str] | None:
        value = self.store.get_state(self.KEY)
        return None if value is None else dict(value)
