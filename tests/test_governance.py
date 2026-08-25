import pytest

from app.hakim import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel


def supported_claim(confidence=0.95):
    return Claim(
        statement="A verified fact",
        confidence=confidence,
        evidence=(Evidence(source="test", statement="Primary evidence", strength=1.0),),
    )


def test_supported_low_risk_action_can_proceed():
    kernel = GovernanceKernel()
    action = Action(name="read_local_state", risk=ActionRisk.LOW)
    assert kernel.evaluate(supported_claim(), action) is Decision.PROCEED


def test_missing_evidence_blocks_even_with_high_confidence():
    kernel = GovernanceKernel()
    claim = Claim(statement="Unsupported assertion", confidence=0.99)
    action = Action(name="read_local_state", risk=ActionRisk.LOW)
    assert kernel.evaluate(claim, action) is Decision.BLOCK


def test_low_confidence_blocks():
    kernel = GovernanceKernel()
    action = Action(name="read_local_state", risk=ActionRisk.LOW)
    assert kernel.evaluate(supported_claim(0.69), action) is Decision.BLOCK


def test_high_risk_requires_approval():
    kernel = GovernanceKernel()
    action = Action(name="send_external_message", risk=ActionRisk.HIGH)
    assert kernel.evaluate(supported_claim(), action) is Decision.APPROVAL_REQUIRED


def test_non_reversible_action_requires_approval():
    kernel = GovernanceKernel()
    action = Action(name="irreversible_change", risk=ActionRisk.MODERATE, reversible=False)
    assert kernel.evaluate(supported_claim(), action) is Decision.APPROVAL_REQUIRED


def test_critical_explicit_approval_is_preserved():
    kernel = GovernanceKernel()
    action = Action(
        name="critical_change",
        risk=ActionRisk.CRITICAL,
        requires_human_approval=True,
    )
    assert kernel.evaluate(supported_claim(), action) is Decision.APPROVAL_REQUIRED


def test_audit_event_is_written_for_each_decision():
    kernel = GovernanceKernel()
    action = Action(name="read_local_state", risk=ActionRisk.LOW)
    kernel.evaluate(supported_claim(), action)
    assert len(kernel.audit_log) == 1
    assert kernel.audit_log[0].event == "decision_gate"


def test_invalid_evidence_strength_is_rejected():
    with pytest.raises(ValueError):
        Evidence(source="test", statement="bad", strength=1.1)
