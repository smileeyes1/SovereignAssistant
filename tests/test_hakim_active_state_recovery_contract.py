from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "governance" / "HAKIM_ACTIVE.json"
STATE = ROOT / "governance" / "HAKIM_ACTIVE_STATE.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_active_state_tracks_current_active_extension_and_main_recovery_path():
    active = load(ACTIVE)
    state = load(STATE)
    assert state["active_extension_version"] == active["version"]
    assert state["candidate_branch"] == "main"
    assert state["status"] == "PRE_FIELD_VERIFIED__PHYSICAL_PHONE_ACTIVATION_PENDING"
    assert state["latest_observed_main"] == state["last_verified_baseline"]
    assert state["latest_observed_main_semantics"].startswith("VERIFIED_PROMOTION_BASELINE_POINTER")
    assert isinstance(state["state_refresh_source_main"], str)
    assert len(state["state_refresh_source_main"]) == 40
    assert state["state_refresh_source_main_semantics"].startswith("SOURCE_MAIN_AT_STATE_REFRESH")


def test_active_state_keeps_physical_phone_claim_fail_closed():
    state = load(STATE)
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["field_verified"] is False
    assert state["field_phone"]["preflight_can_self_promote"] is False
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
    assert "PHYSICAL_PHONE_ROUND_TRIP_NOT_YET_PROVEN" in state["known_failures"]


def test_active_state_restores_max_value_value_gates_and_physical_preflight_gate():
    state = load(STATE)
    assert state["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    assert state["max_value_intent_rule_enforcement"] == "ACTIVE_VERIFIED__RESTORE_AND_PROMOTION_GATE_REQUIRED_ON_2_3_MERGE"
    assert "LOAD_AND_ENFORCE_MAX_VALUE_INTENT_RULE" in state["resume_rule"]
    assert state["value_gates_spec"] == "governance/HAKIM_VALUE_GATES_AR.md"
    gate = state["physical_field_preflight_gate"]
    assert gate == "scripts/android-physical-field-gate.py"
    assert (ROOT / gate).is_file()
    assert state["promotion_evidence"]["value_gates_v1_main"] == "PASS"
    assert state["promotion_evidence"]["physical_field_preflight_gate_v1_main"] == "PASS"
    assert "nstar_adaptive_intelligence_extension_v2_1" in state["proven_success"]
    assert "nstar_adaptive_intelligence_extension_v2_2" in state["proven_success"]
    assert "auditable_android_release_provenance_v1" in state["proven_success"]
    assert "fail_closed_physical_field_preflight_v1" in state["proven_success"]


def test_state_never_contains_secret_material_or_false_field_promotion():
    state = load(STATE)
    assert state["secrets"]["present"] is False
    text = STATE.read_text(encoding="utf-8")
    assert "companion.token" not in text
    assert '"field_verified": true' not in text
    assert "hakim/hc1-over-sovereign-lock" not in text
