from app.hakim.event_continuation import EventType
from app.hakim.run_event_once import _translate


def test_schedule_tick_becomes_unique_mission_liveness_signal():
    event = _translate("123:1", "schedule", {})

    assert event is not None
    assert event.event_id == "watchdog:123:1"
    assert event.event_type == EventType.MANUAL_SIGNAL
    assert event.subject == "mission-liveness-watchdog"
    assert event.payload["scheduled"] is True


def test_unknown_github_event_remains_ignored():
    assert _translate("123:1", "unknown-event", {}) is None
