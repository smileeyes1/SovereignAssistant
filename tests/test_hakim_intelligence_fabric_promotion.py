import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def load(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_intelligence_fabric_promotion_is_verified_durable_and_lineaged():
    promotion = load("HAKIM_INTELLIGENCE_FABRIC_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["version"] == "1.1"
    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert all(value == "PASS" for value in promotion["conditions"].values())
    assert promotion["initial_promoted_main_sha"] == "fed7afae33281cc636f27db302fe412a4c875a28"
    assert promotion["live_gate_promoted_main_sha"] == state["last_verified_baseline"]
    assert state["latest_observed_main"] == promotion["live_gate_promoted_main_sha"]
    assert "adaptive_intelligence_fabric_v1" in state["proven_success"]
    assert "intelligence_fabric_live_execution_gate_v1" in state["proven_success"]
    assert state["promotion_evidence"]["intelligence_fabric_v1_governance_main"] == "PASS"
    assert state["promotion_evidence"]["intelligence_fabric_v1_reality_gate_main"] == "PASS"
    assert state["promotion_evidence"]["intelligence_fabric_live_gate_governance_main"] == "PASS"
    assert state["promotion_evidence"]["intelligence_fabric_live_gate_reality_gate_main"] == "PASS"


def test_live_gate_promotion_proves_routing_without_overclaiming_method_execution():
    promotion = load("HAKIM_INTELLIGENCE_FABRIC_PROMOTION.json")
    live = promotion["live_execution_gate"]
    assert live["status"] == "ACTIVE_VERIFIED"
    assert live["selection_route_before_candidate_choice"] is True
    assert live["execution_route_before_authorization_and_side_effect"] is True
    assert live["direct_executor_entry_routes_intelligence"] is True
    assert live["risk_and_uncertainty_raise_mandatory_guards"] is True
    assert live["durable_selection_and_execution_evidence"] is True
    assert live["routing_is_not_method_execution_proof"] is True
    assert "not that every named reasoning method was executed" in promotion["rule"]


def test_promotion_never_falsifies_physical_phone_status():
    promotion = load("HAKIM_INTELLIGENCE_FABRIC_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["phone_field_verified"] is False
    assert promotion["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
