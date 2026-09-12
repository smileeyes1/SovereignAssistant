import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"
SOURCE_MAIN = "cfd894239c2c6be7e5a423311a96e60588da2db8"


def load(name: str):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_continuity_shield_promotion_is_source_bound_and_verified():
    promotion = load("HAKIM_CONTINUITY_SHIELD_PROMOTION.json")
    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert promotion["source_main"] == SOURCE_MAIN
    assert all(value == "PASS" for value in promotion["proven"].values())


def test_shield_is_active_and_self_protected():
    policy = load("HAKIM_CONTINUITY_SHIELD.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert policy["status"] == "ACTIVE_VERIFIED"
    assert policy["activated_main"] == SOURCE_MAIN
    assert "continuity_shield_v1" in policy["protected_success_ids"]
    assert "continuity_transition_gate_v1" in policy["protected_success_ids"]
    assert "continuity_shield_v1" in policy["protected_promotion_lineage_ids"]
    assert "continuity_shield_v1" in state["proven_success"]
    assert "continuity_transition_gate_v1" in state["proven_success"]
    assert state["promotion_lineage"]["continuity_shield_v1"] == SOURCE_MAIN
    assert state["continuity_shield_promotion"] == "governance/HAKIM_CONTINUITY_SHIELD_PROMOTION.json"


def test_promotion_evidence_covers_independent_and_live_gates():
    state = load("HAKIM_ACTIVE_STATE.json")
    evidence = state["promotion_evidence"]
    for key in (
        "continuity_shield_v1_independent_gate_main",
        "continuity_shield_v1_mutation_tests_main",
        "continuity_shield_v1_governance_main",
        "continuity_shield_v1_reality_gate_main",
        "continuity_shield_v1_live_restart_main",
        "continuity_shield_v1_transition_contract",
    ):
        assert evidence[key] == "PASS"


def test_shield_promotion_never_falsifies_physical_phone_status():
    promotion = load("HAKIM_CONTINUITY_SHIELD_PROMOTION.json")
    state = load("HAKIM_ACTIVE_STATE.json")
    assert promotion["field_phone_verified"] is False
    assert promotion["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"


def test_current_governance_freshness_advances_without_rewriting_historical_promotion_baseline():
    state = load("HAKIM_ACTIVE_STATE.json")
    assert state["governance_verified_main"] == SOURCE_MAIN
    assert state["freshness_observed_main"] == SOURCE_MAIN
    assert state["last_verified_baseline"] == "a6225e4118d68871ed00c8328f072fd8bd15bfc6"
