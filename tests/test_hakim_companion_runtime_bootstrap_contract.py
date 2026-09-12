import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance" / "HAKIM_BRIDGE_POLICY_v2.json"
MAIN = ROOT / "android" / "hakim-companion" / "app" / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion" / "MainActivity.kt"
LOCAL_SERVER = ROOT / "android" / "hakim-companion" / "app" / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion" / "LocalControlServer.kt"
BOOTSTRAP = ROOT / "scripts" / "hakim-complete-phone-bootstrap.sh"
CLOSE = ROOT / "scripts" / "hakim-close-adb-maintenance.sh"
FIELD_START = ROOT / "scripts" / "hakim-field-start.sh"


def test_companion_is_normal_runtime_and_adb_is_conditional_temporary_maintenance():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["phone_execution"] == "ANDROID_COMPANION_PRIMARY"
    assert policy["developer_options_required_for_normal_operation"] is False
    assert policy["normal_operation_requires_adb"] is False
    assert policy["adb_role"] == "TEMPORARY_MAINTENANCE_ONLY"
    assert policy["bootstrap_when_direct_install_blocked"] == "TERMUX_WIRELESS_ADB_ONE_TIME_OR_ON_DEMAND"
    assert policy["close_adb_after_companion_qualification"] is True
    assert policy["public_command_transport"] is False
    assert policy["public_github_command_relay"] == "DISABLED"
    assert policy["security"]["general_remote_shell"] is False
    assert policy["security"]["platform_protection_bypass"] is False
    assert policy["qualification"]["wireless_debugging_pairing"] == "CONDITIONAL_BOOTSTRAP_ONLY_NOT_NORMAL_RUNTIME"


def test_android_ui_has_single_next_step_orchestrator_without_bypassing_sensitive_approvals():
    text = MAIN.read_text(encoding="utf-8")
    assert "أفضل خطوة قادمة — إكمال إعداد حكيم" in text
    assert "Settings.ACTION_ACCESSIBILITY_SETTINGS" in text
    assert "Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS" in text
    assert "requestPermissions" in text
    assert "enabled_accessibility_services" not in text
    assert "ACCESS_RESTRICTED_SETTINGS" not in text


def test_local_control_uses_deterministic_ipv4_loopback_across_network_transitions():
    text = LOCAL_SERVER.read_text(encoding="utf-8")
    assert 'const val LOOPBACK_HOST = "127.0.0.1"' in text
    assert "InetAddress.getByName(LOOPBACK_HOST)" in text
    assert "InetAddress.getLoopbackAddress()" not in text
    assert "0.0.0.0" not in text


def test_bootstrap_signs_installs_configures_waits_approvals_and_retires_maintenance():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    for needle in (
        "install-android-companion-local.sh",
        "apksigner verify",
        "adb -s \"$TARGET\" install -r",
        "hakim://pair?",
        "/v1/status",
        "Authorization: Bearer",
        "APPROVAL_TIMEOUT_SECONDS",
        "LOCAL_ANDROID_APPROVALS_READY",
        "ACTION_NOTIFICATION_LISTENER_SETTINGS",
        "bash \"$CLOSE_MAINT\"",
        "HAKIM_COMPANION_BOOTSTRAP_LOCAL_PHASE_COMPLETE",
    ):
        assert needle in text
    forbidden = (
        "enabled_accessibility_services",
        "ACCESS_RESTRICTED_SETTINGS allow",
        "Play Protect disable",
        "verify_apps_over_usb 0",
        "package_verifier_enable 0",
    )
    for needle in forbidden:
        assert needle not in text


def test_maintenance_closure_is_gated_and_does_not_overclaim_remote_independence():
    text = CLOSE.read_text(encoding="utf-8")
    assert "control_server_listening" in text
    assert "accessibility" in text
    assert "notification_listener" in text
    assert "development_settings_enabled 0" in text
    assert "developer_options_readback_before_transport_close" in text
    assert "adb_wifi_enabled 0" in text
    assert "REQUESTED_AWAITING_COMPANION_ONLY_ROUND_TRIP" in text
    assert "HAKIM_ADB_MAINTENANCE_CLOSE_REQUESTED" in text
    assert "HAKIM_ADB_MAINTENANCE_CLOSED" not in text
    assert text.index("notification_listener") < text.index("adb_wifi_enabled 0")


def test_field_start_is_one_command_orchestrator_and_rejects_public_transport():
    text = FIELD_START.read_text(encoding="utf-8")
    assert "git pull --ff-only" in text
    assert "bootstrap-hakim-termux-adb.sh" in text
    assert "hakim-adb-pair.sh" in text
    assert "hakim-complete-phone-bootstrap.sh" in text
    assert "public_command_transport" in text
    assert "make-private-relay" in text
    assert "HAKIM_RELAY_KEY" in text
    assert "relay_key='" not in text


def test_shell_scripts_parse():
    for path in (BOOTSTRAP, CLOSE, FIELD_START):
        subprocess.run(["bash", "-n", str(path)], check=True)
