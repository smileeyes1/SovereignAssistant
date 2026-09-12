import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = ROOT / "scripts" / "hakim-field-start.sh"
NEXT = ROOT / "scripts" / "android-field-next.sh"
BRIDGE = ROOT / "scripts" / "hakim-termux-adb-bridge.py"
POLICY = ROOT / "governance" / "HAKIM_BRIDGE_POLICY_v2.json"
MAIN = ROOT / "android" / "hakim-companion" / "app" / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion" / "MainActivity.kt"
SERVER = ROOT / "android" / "hakim-companion" / "app" / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion" / "LocalControlServer.kt"


def test_current_field_policy_remains_termux_until_real_evidence():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert p["phone_execution"] == "TERMUX_WIRELESS_ADB_PRIMARY_LOCAL"
    assert p["adb_role"] == "PRIMARY_LOCAL_ALLOWLISTED_CONTROL"
    assert p["qualification"]["field_verified_requires_real_round_trip"] is True
    assert p["security"]["general_remote_shell"] is False
    assert p["public_command_transport"] is False


def test_field_start_is_one_command_private_and_fail_closed():
    s = FIELD.read_text(encoding="utf-8")
    assert "hakim-adb-pair.sh" in s
    assert "hakim-bridges-status" in s
    assert "android-field-next.sh" in s
    assert "make-private-relay" in s
    assert "public_command_transport" in s
    assert "HAKIM_FIELD_BRIDGE_READY" in s
    assert "hakim-control-on" in s
    assert "install-android-companion-local.sh" not in s
    assert "hakim-close-adb-maintenance" not in s
    assert "relay_key='" not in s
    subprocess.run(["bash", "-n", str(FIELD)], check=True)


def test_field_next_sequences_termux_then_companion_candidate():
    s = NEXT.read_text(encoding="utf-8")
    assert "TERMUX_WIRELESS_ADB_LOCAL" in s
    assert "TERMUX_ADB_REAL_FIELD_ROUND_TRIP" in s
    assert "ANDROID_WIRELESS_DEBUGGING_PAIRING" in s
    assert "ANDROID_COMPANION_NO_ADB_RUNTIME" in s
    assert "Never retire ADB" in s
    subprocess.run(["bash", "-n", str(NEXT)], check=True)


def test_termux_bridge_is_signed_allowlisted_and_mutations_local_gated():
    s = BRIDGE.read_text(encoding="utf-8")
    assert 'ALLOWED = {"status", "ui", "screenshot", "notifications", "action", "launch"}' in s
    assert 'READ_ONLY = {"status", "ui", "screenshot", "notifications"}' in s
    assert "HmacSHA256" not in s  # Python implementation uses hmac/hashlib directly.
    assert "hmac.new" in s
    assert "hmac.compare_digest" in s
    assert "expires_at_ms" in s
    assert "claim(" in s
    assert "control_window_open" in s
    assert "local_control_window_closed" in s
    assert "shell=True" not in s
    assert "os.system" not in s


def test_companion_is_candidate_not_false_field_promotion_and_loopback_is_fixed():
    ui = MAIN.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    assert "FIELD الحالي: Termux/ADB" in ui
    assert "لا يُرقّى لمسار التشغيل الحاكم" in ui
    assert "السماح بالإعدادات المقيّدة" in ui
    assert 'const val LOOPBACK_HOST = "127.0.0.1"' in server
    assert "InetAddress.getByName(LOOPBACK_HOST)" in server
    assert "0.0.0.0" not in server
