import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_active_pointer_loads_phone_constraints_before_runtime_and_bridge_policy():
    active = load_json("governance/HAKIM_ACTIVE.json")
    assert active["version"] == "2.3"
    assert active["phone_sovereign_constraints"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    seq = active["restore_sequence"]
    assert "LOAD_PHONE_SOVEREIGN_CONSTRAINTS" in seq
    assert seq.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < seq.index("LOAD_RUNTIME_POLICY")
    assert seq.index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS") < seq.index("LOAD_BRIDGE_POLICY")
    assert "PHONE_SOVEREIGN_CONSTRAINTS_PASS" in active["promotion_gate"]


def test_runtime_preserves_nstar_and_sovereign_local_phone_path():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    assert runtime["sovereign_constraints"]["generic_autonomy_cannot_override"] is True
    control = runtime["device_control"]
    assert control["normal_phone_path"] == "ANDROID_COMPANION_SOVEREIGN_LOCAL_OWNED_BROWSER"
    assert control["developer_options_required_for_normal_operation"] is False
    assert control["wireless_debugging_required_for_normal_operation"] is False
    assert control["accessibility_service_required_for_normal_operation"] is False
    assert control["notification_listener_required_for_normal_operation"] is False
    assert control["external_background_command_transport"] is False
    bridges = runtime["bridges"]
    assert bridges["preferred"] == [
        "ANDROID_COMPANION_LOCAL_LOOPBACK",
        "SIGNED_LOCAL_TASK_DEEPLINK",
        "REMOTE_DESKTOP_MAINTENANCE",
    ]
    assert bridges["maintenance_only"] == ["TERMUX_WIRELESS_ADB"]
    assert bridges["public_command_transport"] is False
    assert bridges["public_github_command_relay"] is False
    assert bridges["external_background_command_transport"] is False
    assert bridges["fallback_command_transport"] == "NONE_IN_NORMAL_OPERATION"
    assert "TERMUX_WIRELESS_ADB" not in bridges["preferred"]


def test_bridge_override_is_fail_closed_and_local_first():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["sovereign_constraint"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert policy["phone_execution"] == "ANDROID_COMPANION_SOVEREIGN_LOCAL_OWNED_BROWSER"
    assert policy["developer_options_required_for_normal_operation"] is False
    assert policy["wireless_debugging_required_for_normal_operation"] is False
    assert policy["accessibility_service_required_for_normal_operation"] is False
    assert policy["notification_listener_required_for_normal_operation"] is False
    assert policy["developer_options_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["wireless_debugging_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["adb_role"] == "TEMPORARY_MAINTENANCE_ONLY_AFTER_EXPLICIT_USER_REQUEST_THEN_OFF"
    assert policy["public_command_transport"] is False
    assert policy["public_ciphertext_carrier_allowed"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["external_background_command_transport"] == "DISABLED"
    assert policy["fallback_command_transport"] == "NONE_IN_NORMAL_OPERATION"
    sec = policy["security"]
    assert sec["loopback_only_control_plane"] is True
    assert sec["signed_local_task_deep_link"] is True
    assert sec["anti_replay"] is True
    assert sec["mutating_actions_fail_closed"] is True
    assert sec["general_remote_shell"] is False
    assert sec["platform_protection_bypass"] is False
    assert policy["qualification"]["wireless_debugging_pairing"] == "NOT_REQUIRED_AND_FORBIDDEN_FOR_NORMAL_OPERATION"


def test_legacy_external_live_bridge_entrypoints_fail_closed():
    for rel in ("scripts/bootstrap-hakim-live-bridge.sh", "scripts/configure-hakim-live-bridge.sh"):
        body = (ROOT / rel).read_text(encoding="utf-8")
        assert "exit 64" in body
        assert "ntfy" not in body.lower()
        assert "relay_key" not in body.lower()
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
