import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_active_pointer_loads_secure_bridge_policy():
    active = load_json("governance/HAKIM_ACTIVE.json")
    assert active["version"] == "2.1"
    assert active["bridge_policy"] == "governance/HAKIM_BRIDGE_POLICY_v2.json"
    assert "LOAD_BRIDGE_POLICY" in active["restore_sequence"]
    assert "LOAD_BRIDGE_HEALTH" in active["restore_sequence"]


def test_runtime_preserves_nstar_and_hybrid_phone_paths():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    assert runtime["device_control"]["normal_phone_path"] == "ANDROID_COMPANION_E2E_ENCRYPTED"
    assert runtime["device_control"]["developer_options_required_for_normal_operation"] is False
    bridges = runtime["bridges"]
    assert bridges["preferred"] == [
        "ANDROID_COMPANION_E2E_ENCRYPTED",
        "TERMUX_WIRELESS_ADB_LOCAL_FIELD",
        "MAKE_PRIVATE_RELAY",
        "RESULT_CHANNEL",
        "REMOTE_DESKTOP_MAINTENANCE",
    ]
    assert bridges["public_command_transport"] is False
    assert bridges["public_ciphertext_carrier_allowed"] is True
    assert bridges["public_github_command_relay"] is False
    assert bridges["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert "GITHUB_OWNER_RELAY" not in bridges["preferred"]


def test_secure_bridge_override_is_fail_closed():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["phone_execution"] == "ANDROID_COMPANION_PRIMARY__TERMUX_FIELD_FALLBACK"
    assert policy["adb_role"] == "FIELD_LOCAL_MAINTENANCE_ONLY"
    assert policy["developer_options_required_for_normal_operation"] is False
    assert policy["public_command_transport"] is False
    assert policy["public_ciphertext_carrier_allowed"] is True
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    sec = policy["security"]
    assert sec["carrier_protocol"] == "HC1"
    assert sec["carrier_content_encryption"] == "AES-256-GCM"
    assert sec["public_carrier_payload"] == "CIPHERTEXT_ONLY"
    assert sec["carrier_plaintext_fallback"] is False
    assert sec["signed_commands"] is True
    assert sec["anti_replay"] is True
    assert sec["expiry_required"] is True
    assert sec["allowlist_only"] is True
    assert sec["mutating_actions_fail_closed"] is True
    assert sec["general_remote_shell"] is False
    assert sec["platform_protection_bypass"] is False
    assert policy["qualification"]["field_verified_requires_real_round_trip"] is True
    assert policy["qualification"]["wireless_debugging_pairing"].startswith("NOT_REQUIRED_FOR_NORMAL_OPERATION")


def test_bootstrap_remains_available_as_local_field_fallback_without_public_plaintext_transport():
    boot = (ROOT / "scripts/bootstrap-hakim-termux-adb.sh").read_text(encoding="utf-8")
    assert "'upstream_bridges':['make-private-relay']" in boot
    assert "'fallback_bridges':[]" in boot
    assert "'public_command_transport':False" in boot
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
