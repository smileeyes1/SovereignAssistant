import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def load(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_best_route_promotion_is_verified_and_durable():
    promotion = load("HAKIM_BEST_ROUTE_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert all(value == "PASS" for value in promotion["conditions"].values())
    assert promotion["promoted_main_sha"] == state["last_verified_baseline"]
    assert state["latest_observed_main"] == promotion["promoted_main_sha"]
    assert "adaptive_best_route_optimizer_v1" in state["proven_success"]
    assert state["promotion_evidence"]["best_route_optimizer_v1_governance_main"] == "PASS"
    assert state["promotion_evidence"]["best_route_optimizer_v1_reality_gate_main"] == "PASS"


def test_best_route_capability_is_not_reduced_to_raw_value_or_false_outcome_proof():
    promotion = load("HAKIM_BEST_ROUTE_PROMOTION.json")
    capability = promotion["capability"]
    assert capability["multicriteria_route_ranking"] is True
    assert capability["method_style_medium_technique_mechanism_timing_audit"] is True
    assert capability["pareto_dominance_guard"] is True
    assert capability["risk_uncertainty_adaptive_weights"] is True
    assert capability["selection_stage_ranking"] is True
    assert capability["execution_boundary_rerank"] is True
    assert capability["ranking_is_not_outcome_proof"] is True


def test_promotion_never_falsifies_phone_field_status():
    promotion = load("HAKIM_BEST_ROUTE_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["phone_field_verified"] is False
    assert promotion["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
