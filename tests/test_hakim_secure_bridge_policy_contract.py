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


def test_runtime_preserves_nstar_and_current_private_field_transport():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    assert runtime["sovereign_constraints"]["generic_autonomy_cannot_override"] is True
    control = runtime["device_control"]
    assert control["governing_phone_path"] == "HAKIM_NATIVE_LOCAL_ADB"
    assert control["bootstrap_owner"] == "HAKIM_ANDROID_APP"
    assert control["third_party_bootstrap_required"] is False
    assert control["termux_role"] == "OPTIONAL_LEGACY_MAINTENANCE_ONLY"
    assert control["wireless_debugging_required_for_governing_local_path"] is True
    assert control["wireless_debugging_pairing"] == "ANDROID_LOCAL_PAIRING_REQUIRED_IF_NOT_ALREADY_TRUSTED"
    assert control["cloud_command_relay"] == "MAKE_PRIVATE_ON_DEMAND_RELAY"
    assert control["result_path"] == "RESULT_MAILBOX"
    bridges = runtime["bridges"]
    assert bridges["preferred"] == [
        "HAKIM_NATIVE_LOCAL_ADB",
        "MAKE_PRIVATE_ON_DEMAND_RELAY",
        "RESULT_MAILBOX",
        "REMOTE_DESKTOP_COMMANDER_OPTIONAL_MAINTENANCE",
        "TERMUX_OPTIONAL_LEGACY_MAINTENANCE",
    ]
    assert bridges["public_command_transport"] is False
    assert bridges["public_github_command_relay"] is False
    assert bridges["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert runtime["security"]["no_general_remote_shell"] is True
    assert runtime["security"]["do_not_disable_platform_protection"] is True
    assert runtime["security"]["do_not_disable_play_protect"] is True


def test_secure_bridge_override_is_fail_closed_and_respects_phone_constraint():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["sovereign_constraint"] == "governance/HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
    assert policy["phone_execution"] == "HAKIM_NATIVE_LOCAL_ADB_GOVERNED"
    assert policy["adb_role"] == "GOVERNING_LOCAL_FIELD_PATH_OWNED_BY_HAKIM_WITH_ANDROID_REQUIRED_LOCAL_PAIRING"
    assert policy["bootstrap_owner"] == "HAKIM_ANDROID_APP"
    assert policy["third_party_bootstrap_required"] is False
    assert policy["termux_role"] == "OPTIONAL_LEGACY_MAINTENANCE_ONLY"
    assert policy["remote_desktop_role"] == "OPTIONAL_MAINTENANCE_ONLY"
    assert policy["public_command_transport"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert policy["security"]["signed_commands"] is True
    assert policy["security"]["anti_replay"] is True
    assert policy["security"]["mutating_actions_fail_closed"] is True
    assert policy["security"]["general_remote_shell"] is False
    assert policy["security"]["platform_protection_bypass"] is False
    assert policy["security"]["play_protect_disable"] is False
    assert policy["qualification"]["field_verified_requires_real_round_trip"] is True


def test_legacy_termux_bootstrap_is_preserved_but_not_governing():
    boot = (ROOT / "scripts/bootstrap-hakim-termux-adb.sh").read_text(encoding="utf-8")
    assert "'public_command_transport':False" in boot
    assert "'transport':'termux-wireless-adb'" in boot
    assert "'upstream_bridges':['make-private-relay']" in boot
    assert "'maintenance_bridges':['remote-desktop-commander']" in boot
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert runtime["bridges"]["preferred"][0] == "HAKIM_NATIVE_LOCAL_ADB"
    assert runtime["device_control"]["adb_policy"] == "LOCAL_GOVERNED_ALLOWLIST_ONLY_NO_GENERAL_REMOTE_SHELL"
    assert policy["qualification"]["termux_wireless_adb"] == "PRESERVED_OPTIONAL_LEGACY_MAINTENANCE_NOT_GOVERNING"
    assert runtime["security"]["no_general_remote_shell"] is True
