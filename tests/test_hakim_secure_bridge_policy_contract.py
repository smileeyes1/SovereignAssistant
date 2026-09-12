import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_active_pointer_loads_phone_constraints_before_runtime_and_bridge_policy():
    active = load_json("governance/HAKIM_ACTIVE.json")
    assert active["version"] == "2.1"
    assert active["phone_sovereign_constraints"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    seq = active["restore_sequence"]
    assert "LOAD_PHONE_SOVEREIGN_CONSTRAINTS" in seq
    assert seq.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < seq.index("LOAD_RUNTIME_POLICY")
    assert seq.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < seq.index("LOAD_BRIDGE_POLICY")
    assert "PHONE_SOVEREIGN_CONSTRAINTS_PASS" in active["promotion_gate"]


def test_runtime_preserves_nstar_and_companion_private_transport():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    assert runtime["sovereign_constraints"]["generic_autonomy_cannot_override"] is True
    assert runtime["device_control"]["normal_phone_path"] == "ANDROID_COMPANION_ACCESSIBILITY_WITH_PRIVATE_RELAY"
    assert runtime["device_control"]["developer_options_required_for_normal_operation"] is False
    assert runtime["device_control"]["wireless_debugging_required_for_normal_operation"] is False
    bridges = runtime["bridges"]
    assert bridges["preferred"] == [
        "ANDROID_COMPANION_OUTBOUND_RELAY",
        "MAKE_PRIVATE_RELAY",
        "RESULT_CHANNEL",
        "REMOTE_DESKTOP_MAINTENANCE",
    ]
    assert bridges["maintenance_only"] == ["TERMUX_WIRELESS_ADB"]
    assert bridges["public_command_transport"] is False
    assert bridges["public_github_command_relay"] is False
    assert bridges["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert "TERMUX_WIRELESS_ADB_LOCAL" not in bridges["preferred"]


def test_secure_bridge_override_is_fail_closed_and_respects_phone_constraint():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["sovereign_constraint"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert policy["phone_execution"] == "ANDROID_COMPANION_PRIMARY"
    assert policy["developer_options_required_for_normal_operation"] is False
    assert policy["wireless_debugging_required_for_normal_operation"] is False
    assert policy["developer_options_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["wireless_debugging_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["adb_role"] == "TEMPORARY_MAINTENANCE_ONLY_AFTER_EXPLICIT_USER_REQUEST_THEN_OFF"
    assert policy["public_command_transport"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert policy["security"]["signed_commands"] is True
    assert policy["security"]["anti_replay"] is True
    assert policy["security"]["mutating_actions_fail_closed"] is True
    assert policy["security"]["general_remote_shell"] is False
    assert policy["security"]["platform_protection_bypass"] is False
    assert policy["qualification"]["wireless_debugging_pairing"] == "NOT_REQUIRED_AND_FORBIDDEN_FOR_NORMAL_OPERATION"


def test_bootstrap_is_not_a_normal_phone_path():
    boot = (ROOT / "scripts/bootstrap-hakim-termux-adb.sh").read_text(encoding="utf-8")
    assert "'public_command_transport':False" in boot
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert "TERMUX_WIRELESS_ADB" not in runtime["bridges"]["preferred"]
    assert runtime["device_control"]["adb_policy"].startswith("TEMPORARY_MAINTENANCE_ONLY")
