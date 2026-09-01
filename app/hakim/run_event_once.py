"""One-shot GitHub event bridge for immediate Ω APEX continuation."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .event_continuation import ContinuationEvent, EventType
from .ingress_supervisor import GitHubEventAdapter
from .run_autonomy import build_runtime_from_env


def _event_file() -> dict[str, object]:
    path = Path(os.environ["GITHUB_EVENT_PATH"])
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GitHub event payload must be an object")
    return value


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
