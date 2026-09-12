"""One-shot GitHub event bridge for immediate Ω APEX continuation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from .event_continuation import ContinuationEvent, EventType
from .ingress_supervisor import GitHubEventAdapter
from .run_autonomy import build_runtime_from_env


_GITHUB_DURABLE_TYPES = (
    EventType.CI_SUCCEEDED,
    EventType.CI_FAILED,
    EventType.PR_MERGED,
)
_STATE_PAYLOAD_TYPES = {
    "omega.development.last_ci_failure": EventType.CI_FAILED,
    "omega.development.last_pr_merged_event": EventType.PR_MERGED,
}


def _event_file() -> dict[str, object]:
    path = Path(os.environ["GITHUB_EVENT_PATH"])
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GitHub event payload must be an object")
    return value


def _decode_payload(raw: str, *, location: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid durable JSON at {location}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"durable GitHub payload must be an object at {location}")
    return value


def _sanitize_legacy_github_payloads(database_path: str | Path) -> int:
    """Minimize previously persisted GitHub envelopes in place, transactionally.

    The event/work identities, statuses, attempts, timestamps and state subjects
    are left untouched. Only JSON payload bodies for known GitHub event types are
    rewritten through the same allow-list used by live ingress. The operation is
    idempotent and fails closed on malformed known GitHub payloads.
    """
    path = Path(database_path)
    if not path.is_file():
        return 0

    adapter = GitHubEventAdapter()
    changed = 0
    type_values = tuple(event_type.value for event_type in _GITHUB_DURABLE_TYPES)
    placeholders = ",".join("?" for _ in type_values)

    with sqlite3.connect(path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        if "work_queue" in tables:
            rows = conn.execute(
                f"SELECT job_id,event_type,payload_json FROM work_queue WHERE event_type IN ({placeholders})",
                type_values,
            ).fetchall()
            for job_id, raw_type, raw_payload in rows:
                event_type = EventType(str(raw_type))
                payload = _decode_payload(str(raw_payload), location=f"work_queue:{job_id}")
                minimized = adapter.minimize_durable_payload(event_type, payload)
                if payload != minimized:
                    conn.execute(
                        "UPDATE work_queue SET payload_json=? WHERE job_id=?",
                        (json.dumps(minimized, ensure_ascii=False, sort_keys=True), job_id),
                    )
                    changed += 1

        if "events" in tables:
            rows = conn.execute(
                f"SELECT event_id,event_type,payload_json FROM events WHERE event_type IN ({placeholders})",
                type_values,
            ).fetchall()
            for event_id, raw_type, raw_payload in rows:
                event_type = EventType(str(raw_type))
                payload = _decode_payload(str(raw_payload), location=f"events:{event_id}")
                minimized = adapter.minimize_durable_payload(event_type, payload)
                if payload != minimized:
                    conn.execute(
                        "UPDATE events SET payload_json=? WHERE event_id=?",
                        (json.dumps(minimized, ensure_ascii=False, sort_keys=True), event_id),
                    )
                    changed += 1

        if "state" in tables:
            keys = tuple(_STATE_PAYLOAD_TYPES)
            key_placeholders = ",".join("?" for _ in keys)
            rows = conn.execute(
                f"SELECT key,value_json FROM state WHERE key IN ({key_placeholders})",
                keys,
            ).fetchall()
            for key, raw_value in rows:
                value = _decode_payload(str(raw_value), location=f"state:{key}")
                payload = value.get("payload")
                if not isinstance(payload, dict):
                    continue
                minimized = adapter.minimize_durable_payload(_STATE_PAYLOAD_TYPES[str(key)], payload)
                if payload != minimized:
                    updated = dict(value)
                    updated["payload"] = minimized
                    conn.execute(
                        "UPDATE state SET value_json=? WHERE key=?",
                        (json.dumps(updated, ensure_ascii=False, sort_keys=True), key),
                    )
                    changed += 1

    return changed


def _translate(delivery: str, event_name: str, payload: dict[str, object]) -> ContinuationEvent | None:
    # A scheduled run is an external deadman signal, not the primary continuation
    # mechanism. It exists solely to recover an unfinished mission if all normal
    # event-driven/same-cycle continuation paths have gone quiet.
    if event_name == "schedule":
        return ContinuationEvent(
            event_id=f"watchdog:{delivery}",
            event_type=EventType.MANUAL_SIGNAL,
            subject="mission-liveness-watchdog",
            payload={"source": "github-deadman-watchdog", "scheduled": True},
        )
    return GitHubEventAdapter().translate(delivery, event_name, payload)


def main() -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    payload = _event_file()
    _sanitize_legacy_github_payloads(os.environ.get("OMEGA_DB_PATH", ".omega/omega.db"))
    runtime = build_runtime_from_env()

    delivery = os.environ.get("GITHUB_RUN_ID", "github-action") + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    translated = _translate(delivery, event_name, payload)
    if translated is None:
        return

    runtime.queue.enqueue(
        translated.event_id,
        translated.event_type.value,
        translated.subject,
        translated.payload,
        max_attempts=5,
    )
    report = runtime.service.supervisor.drain(max_items=100)
    runtime.state.set_state(
        "omega.event_bridge.last_run",
        {
            "event_id": translated.event_id,
            "event_type": translated.event_type.value,
            "subject": translated.subject,
            "processed": report.processed,
            "outcomes": list(report.outcomes),
        },
    )


if __name__ == "__main__":
    main()
