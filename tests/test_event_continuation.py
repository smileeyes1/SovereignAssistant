import pytest

from app.hakim.event_continuation import ActionCandidate, ContinuationEvent, EventDrivenContinuation, EventRouter, EventType


def test_selects_highest_value_eligible_action():
    executed = []
    def source(event):
        return [
            ActionCandidate("unsafe-high", 100, False, True, True),
            ActionCandidate("safe-low", 10, True, True, True),
            ActionCandidate("safe-high", 20, True, True, True),
        ]
    engine = EventDrivenContinuation(source, lambda action, event: executed.append(action.name))
    decision = engine.handle(ContinuationEvent("evt-1", EventType.CI_SUCCEEDED, "pr-4"))
    assert decision.status == "executed"
    assert decision.selected_action == "safe-high"
    assert executed == ["safe-high"]


def test_blocks_when_only_unsafe_or_unauthorized_actions_exist():
    engine = EventDrivenContinuation(
        lambda event: [ActionCandidate("irreversible", 50, True, False, True), ActionCandidate("unauthorized", 40, True, True, False)],
        lambda action, event: pytest.fail("executor must not run"),
    )
    decision = engine.handle(ContinuationEvent("evt-2", EventType.TASK_COMPLETED, "r2"))
    assert decision.status == "blocked"
    assert decision.selected_action is None


def test_duplicate_event_is_idempotent():
    executed = []
    engine = EventDrivenContinuation(lambda event: [ActionCandidate("next", 1, True, True, True)], lambda action, event: executed.append(event.event_id))
    event = ContinuationEvent("evt-3", EventType.PR_MERGED, "r2")
    assert engine.handle(event).status == "executed"
    assert engine.handle(event).status == "ignored"
    assert executed == ["evt-3"]


def test_failed_execution_can_be_retried_with_same_event():
    attempts = {"count": 0}
    def execute(action, event):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
    engine = EventDrivenContinuation(lambda event: [ActionCandidate("retryable", 1, True, True, True)], execute)
    event = ContinuationEvent("evt-4", EventType.CI_FAILED, "build")
    assert engine.handle(event).status == "failed"
    assert engine.handle(event).status == "executed"
    assert attempts["count"] == 2


def test_router_dispatches_immediately_to_subscribers():
    seen = []
    engine = EventDrivenContinuation(lambda event: [ActionCandidate("continue", 1, True, True, True)], lambda action, event: seen.append((action.name, event.subject)))
    router = EventRouter()
    router.subscribe(engine.handle)
    decisions = router.publish(ContinuationEvent("evt-5", EventType.CHECKPOINT_SAVED, "project-x"))
    assert decisions[0].status == "executed"
    assert seen == [("continue", "project-x")]


def test_event_requires_identity_and_subject():
    with pytest.raises(ValueError, match="event_id"):
        ContinuationEvent(" ", EventType.MANUAL_SIGNAL, "x")
    with pytest.raises(ValueError, match="subject"):
        ContinuationEvent("evt", EventType.MANUAL_SIGNAL, " ")
