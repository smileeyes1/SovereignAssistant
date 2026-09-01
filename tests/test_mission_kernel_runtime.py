from pathlib import Path

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.mission_kernel import MissionKernel, OperationalEnvelope
from app.hakim.recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim


def event():
    return ContinuationEvent("evt-1", EventType.MANUAL_SIGNAL, "mission", {})


def action(name="safe", risk=ActionRisk.MODERATE, reversible=True, approval=False):
    return RegisteredAction(
        name=name,
        event_types=(EventType.MANUAL_SIGNAL,),
        value=10,
        risk=risk,
        reversible=reversible,
        requires_human_approval=approval,
        claim_factory=lambda e: strong_claim("observed", "test"),
        executor=lambda e: None,
    )


def test_default_mission_kernel_preserves_safe_existing_path(tmp_path):
    registry = ActionRegistry()
    registry.register(action())
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    candidate = governor.candidates(event())[0]
    assert candidate.safe is True
    assert candidate.authorized is True


def test_runtime_mission_kernel_blocks_critical_action_even_with_strong_claim(tmp_path):
    registry = ActionRegistry()
    registry.register(action("critical", ActionRisk.CRITICAL, True))
    state = DurableStateStore(tmp_path / "omega.db")
    governor = RecoveryGovernor(registry, state)
    candidate = governor.candidates(event())[0]
    assert candidate.safe is False
    denial = state.get_state("omega.mission_kernel.last_denial.critical")
    assert denial["reason"] == "risk exceeds operational envelope"


def test_runtime_mission_kernel_blocks_capability_outside_explicit_envelope(tmp_path):
    registry = ActionRegistry()
    registry.register(action("merge-verified-pr"))
    state = DurableStateStore(tmp_path / "omega.db")
    kernel = MissionKernel(OperationalEnvelope(frozenset({"record-ci-failure"}), max_risk=2, min_evidence=1))
    governor = RecoveryGovernor(registry, state, mission_kernel=kernel)
    candidate = governor.candidates(event())[0]
    assert candidate.safe is False
    denial = state.get_state("omega.mission_kernel.last_denial.merge-verified-pr")
    assert denial["next_phase"] == "degraded"


def test_human_gated_action_never_becomes_autonomously_authorized(tmp_path):
    registry = ActionRegistry()
    registry.register(action("consequential", ActionRisk.MODERATE, True, approval=True))
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    candidate = governor.candidates(event())[0]
    assert candidate.safe is False
    assert candidate.authorized is False
