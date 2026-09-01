import pytest

from app.hakim.mission_kernel import (
    AuthorityLevel,
    MissionAction,
    MissionKernel,
    MissionPhase,
    OperationalEnvelope,
)


def kernel():
    return MissionKernel(
        OperationalEnvelope(
            frozenset({"read", "patch", "rollback"}),
            max_risk=2,
            require_reversible_above=1,
            min_evidence=1,
        )
    )


def test_outside_envelope_fails_closed_into_degraded_mode():
    decision = kernel().evaluate(MissionAction("deploy", "prod-deploy", 1, True, AuthorityLevel.REVERSIBLE, ("test",)))
    assert decision.allowed is False
    assert decision.degraded is True
    assert decision.next_phase == MissionPhase.DEGRADED


def test_irreversible_high_risk_action_is_blocked():
    decision = kernel().evaluate(MissionAction("mutate", "patch", 2, False, AuthorityLevel.MODERATE, ("ci",)))
    assert decision.allowed is False
    assert decision.next_phase == MissionPhase.BLOCKED


def test_consequential_action_requires_human_authority_gate():
    action = MissionAction("critical", "patch", 2, True, AuthorityLevel.CONSEQUENTIAL, ("ci", "review"))
    assert kernel().evaluate(action).allowed is False
    assert kernel().evaluate(action, human_approved=True).allowed is True


def test_missing_evidence_routes_to_recovery():
    decision = kernel().evaluate(MissionAction("patch", "patch", 1, True, AuthorityLevel.REVERSIBLE, ()))
    assert decision.allowed is False
    assert decision.next_phase == MissionPhase.RECOVERING


def test_fallback_prefers_lower_risk_then_stronger_evidence():
    actions = [
        MissionAction("risky", "patch", 2, True, AuthorityLevel.MODERATE, ("a", "b")),
        MissionAction("safe-weak", "rollback", 1, True, AuthorityLevel.REVERSIBLE, ("a",)),
        MissionAction("safe-strong", "rollback", 1, True, AuthorityLevel.REVERSIBLE, ("a", "b")),
    ]
    assert kernel().choose_fallback(actions).name == "safe-strong"


def test_invalid_state_transition_is_rejected():
    control = kernel()
    with pytest.raises(RuntimeError):
        control.transition(MissionPhase.COMPLETED)
    assert control.transition(MissionPhase.PLANNING) == MissionPhase.PLANNING
    assert control.transition(MissionPhase.EXECUTING) == MissionPhase.EXECUTING
