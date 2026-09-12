import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_phone_interface_is_active_verified_single_hakim_without_field_promotion():
    active = load("governance/HAKIM_ACTIVE.json")
    identity = load(active["phone_interface_identity"])
    promotion = load(active["phone_interface_promotion"])
    base_state = load(active["active_state"])
    overlay = load(active["active_state_metadata_overlay"])

    assert active["version"] == "2.3"
    assert identity["status"] == "ACTIVE_VERIFIED"
    assert identity["canonical_instance_id"] == "HAKIM_ORIGINAL_PHONE_APP"
    assert identity["android_application_id"] == "org.hakim.omega.companion"
    assert identity["parallel_hakim_forbidden"] is True
    assert identity["phone_interface_is_same_hakim"] is True
    assert identity["native_local_adb_must_be_preserved"] is True
    assert identity["field_verified"] is False

    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert promotion["verified_merged_main"] == "f054ee0900e8d907b0ce0166b71ab64c83e0d225"
    assert all(value == "PASS" for value in promotion["evidence"].values())
    assert promotion["field_verified"] is False
    assert promotion["physical_phone_round_trip"] == "NOT_PROVEN"

    assert base_state["max_value_intent_rule_enforcement"].startswith("ACTIVE_VERIFIED")
    assert "max_value_intent_rule_v1_1_restored_governing_contract" in base_state["proven_success"]
    assert "max_value_lexical_intensifiers_v1" in base_state["proven_success"]
    assert "autonomous_mutation_guard_v1" in base_state["proven_success"]
    assert base_state["field_phone"]["field_verified"] is False
    assert base_state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"

    assert overlay["status"] == "ACTIVE_VERIFIED"
    assert overlay["scope"].endswith("NO_PHYSICAL_FIELD_STATUS_OVERRIDE")
    assert overlay["governance_verified_main"] == promotion["verified_merged_main"]
    assert overlay["freshness_observed_main"] == promotion["verified_merged_main"]
    assert overlay["freshness_state_refresh_source_main"] == promotion["verified_merged_main"]
    assert "canonical_phone_interface_v1" in overlay["proven_success_additions"]
    assert "android_airplane_recovery_resilience_v1" in overlay["proven_success_additions"]
    assert overlay["field_invariants"]["last_verified_baseline"] == base_state["last_verified_baseline"]
    assert overlay["field_invariants"]["latest_observed_main"] == base_state["latest_observed_main"]
    assert overlay["field_invariants"]["field_verified"] is False
    assert overlay["field_invariants"]["physical_phone_round_trip"] == "NOT_PROVEN"


def test_frozen_restore_and_promotion_sequences_are_not_mutated_by_metadata_overlay():
    active = load("governance/HAKIM_ACTIVE.json")
    assert "LOAD_PHONE_INTERFACE_IDENTITY" not in active["restore_sequence"]
    assert "PHONE_INTERFACE_IDENTITY_CONTRACT_PASS" not in active["promotion_gate"]
    assert active["active_state"] == "governance/HAKIM_ACTIVE_STATE.json"
    assert active["active_state_metadata_overlay"] == "governance/HAKIM_ACTIVE_STATE_METADATA_OVERLAY.json"
