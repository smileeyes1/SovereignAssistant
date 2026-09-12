import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"
SOURCE_MAIN = "a6225e4118d68871ed00c8328f072fd8bd15bfc6"


def load(name: str):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_one_tap_promotion_is_pre_field_and_source_bound():
    promotion = load("HAKIM_ONE_TAP_FIELD_QUALIFICATION_PROMOTION.json")
    assert promotion["status"] == "ACTIVE_VERIFIED_PRE_FIELD"
    assert promotion["source_main"] == SOURCE_MAIN
    assert promotion["not_yet_proven"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert promotion["not_yet_proven"]["field_verified"] is False
    assert promotion["not_yet_proven"]["financial_app_compatibility_on_real_phone"] == "NOT_PROVEN"


def test_active_state_promotes_only_pre_field_capability():
    state = load("HAKIM_ACTIVE_STATE.json")
    assert state["last_verified_baseline"] == SOURCE_MAIN
    assert state["latest_observed_main"] == SOURCE_MAIN
    assert state["state_refresh_source_main"] == SOURCE_MAIN
    assert state["one_tap_field_qualification_promotion"] == "governance/HAKIM_ONE_TAP_FIELD_QUALIFICATION_PROMOTION.json"
    assert "one_tap_field_qualification_v1" in state["proven_success"]
    assert "sanitized_remote_field_qualification_status_v1" in state["proven_success"]
    assert state["promotion_evidence"]["one_tap_field_qualification_v1_governance_main"] == "PASS"
    assert state["promotion_evidence"]["one_tap_field_qualification_v1_reality_gate_main"] == "PASS"
    assert state["promotion_evidence"]["one_tap_field_qualification_android15_emulator"] == "PASS"
    assert state["field_phone"]["one_tap_self_qualification"] == "ACTIVE_VERIFIED_PRE_FIELD"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"


def test_next_gate_remains_physical_and_fail_closed():
    state = load("HAKIM_ACTIVE_STATE.json")
    next_gate = state["field_phone"]["next_gate"]
    assert "PHYSICAL_PHONE" in next_gate
    assert "PRIVATE_PAIR" in next_gate
    assert "SCREEN_OFF_REBOOT_FINANCIAL_MATRIX" in next_gate
    assert "PHYSICAL_PHONE_ROUND_TRIP_NOT_YET_PROVEN" in state["known_failures"]
    assert state["secrets"]["present"] is False
