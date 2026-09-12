from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.event_continuation import ActionCandidate, ContinuationEvent, EventType
from app.hakim.recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim


def registered(name, executor, *, risk=ActionRisk.LOW, event_type=EventType.TASK_FAILED):
    return RegisteredAction(
        name=name,
        event_types=(event_type,),
        value=10,
        risk=risk,
        reversible=True,
        requires_human_approval=False,
        claim_factory=lambda event: strong_claim("direct runtime evidence"),
        executor=executor,
    )


def selected_names(route):
    return {item["family"] for item in route["selected"]}


def test_live_candidate_selection_routes_and_persists_failure_intelligence(tmp_path):
    state = DurableStateStore(tmp_path / "omega.db")
    registry = ActionRegistry()
    registry.register(registered("repair", lambda event: None))
    governor = RecoveryGovernor(registry, state)
    event = ContinuationEvent("fabric-selection", EventType.TASK_FAILED, "repair mission")

    candidates = governor.candidates(event)

    assert candidates
    route = governor.intelligence_route(event.event_id, "selection")
    assert route is not None
    assert route["status"] == "ROUTED_NOT_METHOD_EXECUTION_PROOF"
    assert route["stage"] == "selection"
    names = selected_names(route)
    assert {"intent_contract", "operational_execution", "memory_learning", "metacognitive", "simplicity_economy"} <= names
    assert {"causal_counterfactual", "creative", "evidence"} <= names
    assert route["composition"][0] == "intent_contract"


def test_high_risk_candidate_forces_risk_intelligence_even_when_action_is_denied(tmp_path):
    state = DurableStateStore(tmp_path / "omega.db")
    registry = ActionRegistry()
    registry.register(registered("high-risk-repair", lambda event: None, risk=ActionRisk.HIGH))
    governor = RecoveryGovernor(registry, state)
    event = ContinuationEvent("fabric-high-risk", EventType.TASK_FAILED, "high risk mission")

    governor.candidates(event)

    route = governor.intelligence_route(event.event_id, "selection")
    assert route is not None
    assert route["request"]["risk"] == 2
    assert {"evidence", "adversarial", "decision_strategy", "security_privacy"} <= selected_names(route)


def test_execution_boundary_recomputes_route_before_real_side_effect(tmp_path):
    state = DurableStateStore(tmp_path / "omega.db")
    registry = ActionRegistry()
    observed = []
    governor_holder = {}

    def executor(event):
        governor = governor_holder["governor"]
        route = governor.intelligence_route(event.event_id, "execution")
        observed.append(route)

    registry.register(registered("execute", executor))
    governor = RecoveryGovernor(registry, state)
    governor_holder["governor"] = governor
    event = ContinuationEvent("fabric-execution", EventType.TASK_FAILED, "execution mission")

    result = governor.engine().handle(event)

    assert result.status == "executed"
    assert len(observed) == 1
    assert observed[0] is not None
    assert observed[0]["stage"] == "execution"
    assert "operational_execution" in selected_names(observed[0])
    assert governor.intelligence_route(event.event_id, "selection") is not None


def test_direct_executor_entry_cannot_bypass_intelligence_route(tmp_path):
    state = DurableStateStore(tmp_path / "omega.db")
    registry = ActionRegistry()
    seen = []
    registry.register(registered("direct", lambda event: seen.append("ran")))
    governor = RecoveryGovernor(registry, state)
    event = ContinuationEvent("fabric-direct", EventType.TASK_FAILED, "direct mission")
    forged = ActionCandidate("direct", 999, safe=True, reversible=True, authorized=True, ready=True)

    governor.execute(forged, event)

    assert seen == ["ran"]
    route = governor.intelligence_route(event.event_id, "execution")
    assert route is not None
    assert route["status"] == "ROUTED_NOT_METHOD_EXECUTION_PROOF"
    assert {"operational_execution", "memory_learning"} <= selected_names(route)


def test_payload_uncertainty_and_explicit_signals_only_add_stronger_routing(tmp_path):
    state = DurableStateStore(tmp_path / "omega.db")
    registry = ActionRegistry()
    registry.register(registered("analyze", lambda event: None, event_type=EventType.MANUAL_SIGNAL))
    governor = RecoveryGovernor(registry, state)
    event = ContinuationEvent(
        "fabric-uncertain",
        EventType.MANUAL_SIGNAL,
        "uncertain mission",
        {"uncertainty": 0.91, "intelligence_signals": ["forecast", "security", "improvement"]},
    )

    governor.candidates(event)

    route = governor.intelligence_route(event.event_id, "selection")
    assert route is not None
    names = selected_names(route)
    assert {"evidence", "probabilistic", "temporal_future", "security_privacy", "experimental_measurement"} <= names
    assert route["request"]["uncertainty"] == 0.91
