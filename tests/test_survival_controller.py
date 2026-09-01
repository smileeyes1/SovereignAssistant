from app.hakim.durable_state import DurableStateStore
from app.hakim.survival_controller import FailureClass, OperatingMode, SurvivalController


def test_capability_loss_enters_durable_degraded_mode_with_explicit_fallback(tmp_path):
    db = tmp_path / "omega.db"
    first = SurvivalController(DurableStateStore(db))
    decision = first.diagnose("primary-provider", FailureClass.CAPABILITY_LOSS, fallback="secondary-provider")
    assert decision.mode == OperatingMode.DEGRADED
    assert decision.isolated
    assert decision.recovery == "failover"
    assert decision.fallback == "secondary-provider"

    restarted = SurvivalController(DurableStateStore(db))
    assert restarted.status("primary-provider")["mode"] == "degraded"
    assert restarted.status("primary-provider")["fallback"] == "secondary-provider"


def test_safety_violation_is_fail_closed_even_when_fallback_is_supplied(tmp_path):
    controller = SurvivalController(DurableStateStore(tmp_path / "omega.db"))
    decision = controller.diagnose("unsafe-tool", FailureClass.SAFETY_VIOLATION, fallback="other-tool")
    assert decision.mode == OperatingMode.BLOCKED
    assert decision.recovery == "fail-closed"
    assert decision.fallback is None


def test_state_corruption_never_degrades_to_unverified_operation(tmp_path):
    controller = SurvivalController(DurableStateStore(tmp_path / "omega.db"))
    decision = controller.diagnose("mission-state", FailureClass.STATE_CORRUPTION, fallback="cache")
    assert decision.mode == OperatingMode.BLOCKED
    assert decision.recovery == "fail-closed"


def test_healthy_signal_restores_normal_mode(tmp_path):
    controller = SurvivalController(DurableStateStore(tmp_path / "omega.db"))
    controller.diagnose("provider", FailureClass.TRANSIENT, fallback="backup")
    assert controller.recover("provider") == OperatingMode.NORMAL
    assert controller.status("provider")["mode"] == "normal"
    assert controller.status("provider")["isolated"] is False
