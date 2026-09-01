"""One-shot GitHub event bridge for immediate Ω APEX continuation."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .event_continuation import EventType
from .ingress_supervisor import GitHubEventAdapter
from .run_autonomy import build_runtime_from_env


def _event_file() -> dict[str, object]:
    path = Path(os.environ["GITHUB_EVENT_PATH"])
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GitHub event payload must be an object")
    return value


def main() -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    payload = _event_file()
    runtime = build_runtime_from_env()

    delivery = os.environ.get("GITHUB_RUN_ID", "github-action") + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    translated = GitHubEventAdapter().translate(delivery, event_name, payload)
    if translated is None:
        # workflow_run events and merged PRs are the only continuation triggers here.
        return

    runtime.queue.enqueue(
        translated.event_id,
        translated.event_type.value,
        translated.subject,
        translated.payload,
        max_attempts=5,
    )
    report = runtime.supervisor.drain(max_items=100)
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
