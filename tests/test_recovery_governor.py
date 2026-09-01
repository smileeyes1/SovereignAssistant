from app.hakim.core import ActionRisk, Claim
from app.hakim.durable_state import DurableStateStore
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim


def action(name, value, executor, *, risk=ActionRisk.LOW, reversible=True, approval=False, claim_factory=None):
    return RegisteredAction(
        name=name,
        event_types=(EventType.TASK_FAILED,),
        value=value,
        risk=risk,
        reversible=reversible,
        requires_human_approval=approval,
        claim_factory=claim_factory or (lambda event: strong_claim("observed failure")),
        executor=executor,
    )


def test_highest_value_governed_action_executes(tmp_path):
    seen = []
    registry = ActionRegistry()
    registry.register(action("low", 1, lambda event: seen.append("low")))
    registry.register(action("high", 10, lambda event: seen.append("high")))
    engine = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db")).engine()
    result = engine.handle(ContinuationEvent("e1", EventType.TASK_FAILED, "task"))
    assert result.status == "executed"
    assert result.selected_action == "high"
    assert seen == ["high"]


def test_sensitive_action_stays_behind_human_gate(tmp_path):
    registry = ActionRegistry()
    registry.register(action("dangerous", 100, lambda event: None, risk=ActionRisk.HIGH))
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    result = governor.engine().handle(ContinuationEvent("e2", EventType.TASK_FAILED, "task"))
    assert result.status == "blocked"


def test_unsupported_claim_is_not_executable(tmp_path):
    registry = ActionRegistry()
    registry.register(action("unsupported", 1, lambda event: None, claim_factory=lambda event: Claim("guess", (), 1.0)))
    result = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db")).engine().handle(
        ContinuationEvent("e3", EventType.TASK_FAILED, "task")
    )
    assert result.status == "blocked"


def test_repeated_failure_switches_to_alternative_path(tmp_path):
    seen = []
    registry = ActionRegistry()

    def broken(event):
        seen.append("primary")
        raise RuntimeError("still broken")

    registry.register(action("primary", 10, broken))
    registry.register(action("fallback", 5, lambda event: seen.append("fallback")))
    state = DurableStateStore(tmp_path / "omega.db")
    governor = RecoveryGovernor(registry, state, max_failures_per_path=1)
    event = ContinuationEvent("e4", EventType.TASK_FAILED, "task")

    first = governor.engine().handle(event)
    assert first.status == "failed"
    assert governor.failure_count("e4", "primary") == 1

    second = governor.engine().handle(event)
    assert second.status == "executed"
    assert second.selected_action == "fallback"
    assert seen == ["primary", "fallback"]


def test_failure_memory_survives_governor_restart(tmp_path):
    db = tmp_path / "omega.db"
    registry = ActionRegistry()
    registry.register(action("primary", 10, lambda event: (_ for _ in ()).throw(RuntimeError("x"))))
    registry.register(action("fallback", 5, lambda event: None))
    event = ContinuationEvent("e5", EventType.TASK_FAILED, "task")
    first = RecoveryGovernor(registry, DurableStateStore(db), max_failures_per_path=1)
    assert first.engine().handle(event).status == "failed"
    restarted = RecoveryGovernor(registry, DurableStateStore(db), max_failures_per_path=1)
    result = restarted.engine().handle(event)
    assert result.status == "executed"
    assert result.selected_action == "fallback"
