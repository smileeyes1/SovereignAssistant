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


def test_runtime_preserves_nstar_and_prefers_private_make_transport():
    runtime = load_json("governance/HAKIM_RUNTIME_POLICY_v2.json")
    assert runtime["adaptive_intelligence"]["name"] == "NSTAR"
    assert runtime["adaptive_intelligence"]["extension_version"] == "2.1"
    bridges = runtime["bridges"]
    assert bridges["preferred"] == [
        "LOCAL_DEVICE_BRIDGE",
        "MAKE_PRIVATE_RELAY",
        "RESULT_CHANNEL",
        "REMOTE_DESKTOP_MAINTENANCE",
    ]
    assert bridges["public_command_transport"] is False
    assert bridges["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert "GITHUB_OWNER_RELAY" not in bridges["preferred"]


def test_secure_bridge_override_is_fail_closed():
    policy = load_json("governance/HAKIM_BRIDGE_POLICY_v2.json")
    assert policy["status"] == "ACTIVE_OVERRIDE"
    assert policy["public_command_transport"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["fallback_command_transport"] == "PRIVATE_OR_ENCRYPTED_ONLY"
    assert policy["security"]["signed_commands"] is True
    assert policy["security"]["anti_replay"] is True
    assert policy["security"]["mutating_actions_fail_closed"] is True
    assert policy["security"]["general_remote_shell"] is False
    assert policy["security"]["platform_protection_bypass"] is False


def test_bootstrap_matches_private_bridge_policy():
    boot = (ROOT / "scripts/bootstrap-hakim-termux-adb.sh").read_text(encoding="utf-8")
    assert "'upstream_bridges':['make-private-relay']" in boot
    assert "'fallback_bridges':[]" in boot
    assert "'public_command_transport':False" in boot
    assert not (ROOT / ".github/workflows/hakim-phone-relay.yml").exists()
