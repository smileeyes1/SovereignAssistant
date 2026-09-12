from app.hakim.best_route_optimizer import RouteProfile
from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim


def action(name, value, seen, profile):
    return RegisteredAction(
        name=name,
        event_types=(EventType.TASK_FAILED,),
        value=value,
        risk=ActionRisk.LOW,
        reversible=True,
        requires_human_approval=False,
        claim_factory=lambda event: strong_claim("runtime evidence"),
        executor=lambda event: seen.append(name),
        route_profile=profile,
    )


def test_runtime_chooses_best_multicriteria_route_not_merely_highest_raw_value(tmp_path):
    seen = []
    registry = ActionRegistry()
    registry.register(
        action(
            "high-raw-poor-route",
            100,
            seen,
            RouteProfile(
                method="large_but_weak",
                style="complex",
                medium="external",
                technique="fragile",
                mechanism="high_dependency",
                timing="fast",
                fit=0.2,
                evidence=0.2,
                expected_success=0.2,
                safety_margin=0.3,
                burden=0.9,
                monetary_cost=0.8,
                external_dependency=0.9,
                independence=0.1,
                sustainability=0.2,
                speed=0.9,
            ),
        )
    )
    registry.register(
        action(
            "lower-raw-proven-route",
            60,
            seen,
            RouteProfile(
                method="proven_direct",
                style="minimal",
                medium="local",
                technique="verified",
                mechanism="durable",
                timing="now",
                fit=0.98,
                evidence=0.98,
                expected_success=0.96,
                safety_margin=0.98,
                burden=0.05,
                monetary_cost=0.0,
                external_dependency=0.05,
                independence=0.95,
                sustainability=0.96,
                speed=0.8,
            ),
        )
    )
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    event = ContinuationEvent("best-live", EventType.TASK_FAILED, "repair", {"uncertainty": 0.7})

    result = governor.engine().handle(event)

    assert result.status == "executed"
    assert result.selected_action == "lower-raw-proven-route"
    assert seen == ["lower-raw-proven-route"]
    audit = governor.best_route_assessment(event.event_id, "selection")
    assert audit is not None
    assert audit["status"] == "RANKED_NOT_OUTCOME_PROOF"
    assert audit["winner"] == "lower-raw-proven-route"
    assert "pareto_dominance" in audit["criteria"]


def test_route_audit_contains_method_style_medium_technique_mechanism_and_timing(tmp_path):
    registry = ActionRegistry()
    registry.register(
        RegisteredAction(
            name="described",
            event_types=(EventType.TASK_FAILED,),
            value=10,
            risk=ActionRisk.LOW,
            reversible=True,
            requires_human_approval=False,
            claim_factory=lambda event: strong_claim("runtime evidence"),
            executor=lambda event: None,
            route_profile=RouteProfile(
                method="method-x",
                style="style-x",
                medium="medium-x",
                technique="technique-x",
                mechanism="mechanism-x",
                timing="timing-x",
            ),
        )
    )
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    event = ContinuationEvent("route-shape", EventType.TASK_FAILED, "task")

    governor.candidates(event)

    audit = governor.best_route_assessment(event.event_id)
    route = audit["assessments"][0]["route"]
    assert route["method"] == "method-x"
    assert route["style"] == "style-x"
    assert route["medium"] == "medium-x"
    assert route["technique"] == "technique-x"
    assert route["mechanism"] == "mechanism-x"
    assert route["timing"] == "timing-x"


def test_execution_boundary_recomputes_best_route_audit(tmp_path):
    registry = ActionRegistry()
    registry.register(
        RegisteredAction(
            name="route",
            event_types=(EventType.TASK_FAILED,),
            value=10,
            risk=ActionRisk.LOW,
            reversible=True,
            requires_human_approval=False,
            claim_factory=lambda event: strong_claim("runtime evidence"),
            executor=lambda event: None,
        )
    )
    governor = RecoveryGovernor(registry, DurableStateStore(tmp_path / "omega.db"))
    event = ContinuationEvent("boundary-rank", EventType.TASK_FAILED, "task")

    result = governor.engine().handle(event)

    assert result.status == "executed"
    assert governor.best_route_assessment(event.event_id, "selection") is not None
    execution = governor.best_route_assessment(event.event_id, "execution")
    assert execution is not None
    assert execution["stage"] == "execution"
