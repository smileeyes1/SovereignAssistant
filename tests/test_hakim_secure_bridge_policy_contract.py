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


def test_runtime_preserves_nstar_and_sovereign_local_zero_relay_transport_policy():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    assert runtime["sovereign_constraints"]["generic_autonomy_cannot_override"] is True
    assert runtime["device_control"]["normal_phone_path"] == "SOVEREIGN_LOCAL_ANDROID_COMPANION_WITH_LOOPBACK_BROWSER_AND_USER_OPENED_SIGNED_TASK_LINK"
    assert runtime["device_control"]["developer_options_required_for_normal_operation"] is False
    assert runtime["device_control"]["wireless_debugging_required_for_normal_operation"] is False
    assert runtime["device_control"]["background_external_transport"] == "DISABLED_BY_DEFAULT"
    bridges = runtime["bridges"]
    assert bridges["core_requires_bridge"] is False
    assert bridges["local_core_first"] is True
    assert bridges["runtime_default"] == ["LOCAL_LOOPBACK_CONTROL", "USER_OPENED_SIGNED_TASK_LINK"]
    assert bridges["public_command_transport"] is False
    assert bridges["public_github_command_relay"] is False
    for forbidden in ("MAKE", "TINYFISH", "NTFY", "PAID_API", "PAID_OPERATION_CREDITS"):
        assert forbidden in bridges["forbidden_as_hidden_runtime_core"]


def test_secure_bridge_override_is_fail_closed_and_respects_phone_constraint():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["sovereign_constraint"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert policy["core"]["phone_execution"] == "SOVEREIGN_LOCAL_ANDROID_COMPANION"
    assert policy["core"]["local_control_server"] == "127.0.0.1_ONLY"
    assert policy["core"]["background_external_transport"] == "NONE"
    assert policy["developer_options_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["wireless_debugging_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert policy["adb_role"] == "TEMPORARY_MAINTENANCE_ONLY_AFTER_EXPLICIT_USER_REQUEST_THEN_OFF"
    assert policy["public_command_transport"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["fallback_command_transport"] == "NONE_BY_DEFAULT"
    assert policy["security"]["signed_tasks"] is True
    assert policy["security"]["anti_replay"] is True
    assert policy["security"]["general_remote_shell"] is False
    assert policy["security"]["platform_protection_bypass"] is False
    assert policy["optional_bridge_rule"]["must_be_replaceable"] is True
    assert policy["optional_bridge_rule"]["must_be_disableable_without_reinstall"] is True


def test_bootstrap_is_not_a_normal_phone_path():
    boot = (ROOT / "scripts/bootstrap-hakim-termux-adb.sh").read_text(encoding="utf-8")
    assert "'public_command_transport':False" in boot
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert "TERMUX_WIRELESS_ADB_EXPLICIT_TEMPORARY_MAINTENANCE_ONLY" in runtime["bridges"]["optional_non_core_only"]
    assert runtime["device_control"]["adb_policy"].startswith("TEMPORARY_MAINTENANCE_ONLY")
    assert runtime["bridges"]["core_requires_bridge"] is False
