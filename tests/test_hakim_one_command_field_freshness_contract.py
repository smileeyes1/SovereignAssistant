import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "governance" / "HAKIM_ACTIVE_STATE.json"
VERIFIED_MAIN = "2b5f8ceb8570c889b25f900bcec1600757cf8fa1"
FROZEN_PROMOTION = "a6225e4118d68871ed00c8328f072fd8bd15bfc6"


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8"))


def test_repository_freshness_advances_without_rewriting_frozen_promotion():
    state = load_state()
    assert state["last_verified_baseline"] == FROZEN_PROMOTION
    assert state["latest_observed_main"] == FROZEN_PROMOTION
    assert state["state_refresh_source_main"] == FROZEN_PROMOTION
    assert state["governance_verified_main"] == VERIFIED_MAIN
    assert state["freshness_observed_main"] == VERIFIED_MAIN
    assert state["freshness_state_refresh_source_main"] == VERIFIED_MAIN
    assert state["promotion_lineage"]["one_command_phone_field_v1"] == VERIFIED_MAIN


def test_one_command_path_is_proven_only_as_pre_field_orchestrator():
    state = load_state()
    assert state["pre_field_orchestrator"] == "scripts/hakim-phone-field-run.sh"
    role = state["pre_field_orchestrator_role"]
    assert "DOES_NOT_REPLACE_TERMUX_WIRELESS_ADB_GOVERNING_FIELD_PATH" in role
    assert "DOES_NOT_SELF_PROMOTE_FIELD_VERIFIED" in role
    assert state["field_phone"]["primary_path"] == "TERMUX_WIRELESS_ADB_LOCAL"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"


def test_one_command_verified_evidence_is_durable_and_fail_closed():
    state = load_state()
    for key in (
        "one_command_phone_field_v1_governance_main",
        "one_command_phone_field_v1_reality_gate_main",
        "one_command_phone_field_v1_android_build_and_android15",
        "one_command_phone_field_v1_release_provenance",
        "one_command_phone_field_v1_storage_permission_fail_closed",
    ):
        assert state["promotion_evidence"][key] == "PASS"
    assert "one_command_phone_field_v1_verified" in state["proven_success"]
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
    assert state["secrets"]["present"] is False
