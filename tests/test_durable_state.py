from app.hakim.durable_state import DurableStateStore, ResumeCursor


def test_state_survives_reopen(tmp_path):
    db = tmp_path / "omega.db"
    first = DurableStateStore(db)
    first.set_state("project", {"release": "R3", "ok": True})
    second = DurableStateStore(db)
    assert second.get_state("project") == {"ok": True, "release": "R3"}


def test_events_are_idempotent_and_persist(tmp_path):
    db = tmp_path / "omega.db"
    store = DurableStateStore(db)
    assert store.append_event("e1", "ci_succeeded", "pr-6", {"sha": "abc"})
    assert not store.append_event("e1", "ci_succeeded", "pr-6", {"sha": "abc"})
    reopened = DurableStateStore(db)
    pending = reopened.pending_events()
    assert [event.event_id for event in pending] == ["e1"]
    assert pending[0].payload == {"sha": "abc"}


def test_processed_event_does_not_reappear(tmp_path):
    store = DurableStateStore(tmp_path / "omega.db")
    store.append_event("e1", "task_completed", "r3")
    assert store.mark_processed("e1")
    assert not store.mark_processed("e1")
    assert store.pending_events() == []
    assert list(store.all_events())[0].processed is True


def test_resume_cursor_survives_restart(tmp_path):
    db = tmp_path / "omega.db"
    cursor = ResumeCursor(DurableStateStore(db))
    cursor.save(release="R3", task="durable-state", checkpoint="cp-1", next_action="resume-worker")
    restored = ResumeCursor(DurableStateStore(db)).load()
    assert restored == {
        "release": "R3",
        "task": "durable-state",
        "checkpoint": "cp-1",
        "next_action": "resume-worker",
    }


def test_invalid_event_identity_is_rejected(tmp_path):
    store = DurableStateStore(tmp_path / "omega.db")
    for args in [("", "type", "subject"), ("e", "", "subject"), ("e", "type", "")]:
        try:
            store.append_event(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid event was accepted")
