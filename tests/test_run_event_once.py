import json

from app.hakim.durable_state import DurableStateStore
from app.hakim.durable_worker import DurableWorkQueue
from app.hakim.event_continuation import EventType
from app.hakim.run_event_once import _sanitize_legacy_github_payloads, _translate


def test_schedule_tick_becomes_unique_mission_liveness_signal():
    event = _translate("123:1", "schedule", {})

    assert event is not None
    assert event.event_id == "watchdog:123:1"
    assert event.event_type == EventType.MANUAL_SIGNAL
    assert event.subject == "mission-liveness-watchdog"
    assert event.payload["scheduled"] is True


def test_unknown_github_event_remains_ignored():
    assert _translate("123:1", "unknown-event", {}) is None


def test_legacy_github_payloads_are_minimized_transactionally_and_idempotently(tmp_path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    queue = DurableWorkQueue(db)

    raw_workflow = {
        "action": "completed",
        "sender": {"email": "sender@example.invalid", "token": "do-not-keep"},
        "repository": {"private": True, "description": "do-not-keep-repository"},
        "workflow_run": {
            "id": 501,
            "conclusion": "failure",
            "head_sha": "sha501",
            "actor": {"email": "actor@example.invalid"},
            "pull_requests": [{"number": 31, "body": "do-not-keep-pr-body"}],
        },
    }
    raw_pr = {
        "action": "closed",
        "sender": {"email": "merge-sender@example.invalid"},
        "pull_request": {
            "number": 8,
            "merged": True,
            "merge_commit_sha": "merge8",
            "title": "do-not-keep-title",
            "body": "do-not-keep-merge-body",
        },
    }

    assert queue.enqueue("old-ci", EventType.CI_FAILED.value, "sha501", raw_workflow)
    assert state.append_event("old-pr", EventType.PR_MERGED.value, "8", raw_pr)
    state.set_state(
        "omega.development.last_ci_failure",
        {"subject": "sha501", "payload": raw_workflow},
    )
    state.set_state(
        "omega.development.last_pr_merged_event",
        {"subject": "8", "payload": raw_pr},
    )

    assert _sanitize_legacy_github_payloads(db) == 4
    assert _sanitize_legacy_github_payloads(db) == 0

    expected_workflow = {
        "action": "completed",
        "workflow_run": {
            "id": 501,
            "conclusion": "failure",
            "head_sha": "sha501",
            "pull_requests": [{"number": 31}],
        },
    }
    expected_pr = {
        "action": "closed",
        "pull_request": {
            "number": 8,
            "merged": True,
            "merge_commit_sha": "merge8",
        },
    }

    stored_work = queue.get("old-ci")
    assert stored_work is not None and stored_work.payload == expected_workflow
    stored_events = list(state.all_events())
    assert len(stored_events) == 1 and stored_events[0].payload == expected_pr
    assert state.get_state("omega.development.last_ci_failure") == {
        "subject": "sha501",
        "payload": expected_workflow,
    }
    assert state.get_state("omega.development.last_pr_merged_event") == {
        "subject": "8",
        "payload": expected_pr,
    }

    durable_view = json.dumps(
        {
            "work": stored_work.payload,
            "events": [event.payload for event in stored_events],
            "failure": state.get_state("omega.development.last_ci_failure"),
            "merged": state.get_state("omega.development.last_pr_merged_event"),
        },
        sort_keys=True,
    )
    for forbidden in (
        "sender@example.invalid",
        "do-not-keep",
        "do-not-keep-repository",
        "actor@example.invalid",
        "do-not-keep-pr-body",
        "merge-sender@example.invalid",
        "do-not-keep-title",
        "do-not-keep-merge-body",
    ):
        assert forbidden not in durable_view
