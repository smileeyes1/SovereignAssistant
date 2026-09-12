import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def load(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_intelligence_fabric_promotion_is_verified_and_durable():
    promotion = load("HAKIM_INTELLIGENCE_FABRIC_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert all(value == "PASS" for value in promotion["conditions"].values())
    assert promotion["promoted_main_sha"] == state["last_verified_baseline"]
    assert state["latest_observed_main"] == promotion["promoted_main_sha"]
    assert "adaptive_intelligence_fabric_v1" in state["proven_success"]
    assert state["promotion_evidence"]["intelligence_fabric_v1_governance_main"] == "PASS"
    assert state["promotion_evidence"]["intelligence_fabric_v1_reality_gate_main"] == "PASS"


def test_promotion_never_falsifies_physical_phone_status():
    promotion = load("HAKIM_INTELLIGENCE_FABRIC_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["phone_field_verified"] is False
    assert promotion["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
