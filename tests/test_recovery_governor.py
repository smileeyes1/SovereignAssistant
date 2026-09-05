import pytest

from app.hakim.core import ActionRisk, Claim
from app.hakim.durable_state import DurableStateStore
from app.hakim.event_continuation import ActionCandidate, ContinuationEvent, EventType
from app.hakim.mission_kernel import MissionKernel, OperationalEnvelope
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


def test_execution_boundary_rechecks_governance_against_toctou(tmp_path):
    """A candidate that was safe at selection must not retain stale authority."""
    seen = []
    calls = 0

    def changing_claim(event):
        nonlocal calls
        calls += 1
        if calls == 1:
            return strong_claim("fresh evidence")
        return Claim("evidence disappeared", (), 1.0)

    registry = ActionRegistry()
    registry.register(action("mutable-evidence", 10, lambda event: seen.append("executed"), claim_factory=changing_claim))
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))

    result = governor.engine().handle(ContinuationEvent("e6", EventType.TASK_FAILED, "task"))

    assert result.status == "failed"
    assert "execution-time authorization failed" in result.reason
    assert seen == []
    assert calls == 2


def test_forged_candidate_cannot_bypass_runtime_mission_kernel(tmp_path):
    """Direct executor entry is fail-closed even with a forged executable candidate."""
    seen = []
    registry = ActionRegistry()
    registry.register(action("forbidden-capability", 10, lambda event: seen.append("executed")))
    mission = MissionKernel(
        OperationalEnvelope(
            allowed_capabilities=frozenset({"different-capability"}),
            max_risk=2,
            require_reversible_above=1,
            min_evidence=1,
        )
    )
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"), mission_kernel=mission)
    forged = ActionCandidate("forbidden-capability", 999, safe=True, reversible=True, authorized=True, ready=True)
    event = ContinuationEvent("e7", EventType.TASK_FAILED, "task")

    with pytest.raises(PermissionError, match="execution-time authorization failed"):
        governor.execute(forged, event)

    assert seen == []
    denial = governor.state.get_state("omega.mission_kernel.last_denial.forbidden-capability")
    assert denial["event_id"] == "e7"
