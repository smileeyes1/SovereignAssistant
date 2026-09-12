from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app" / "src" / "main"
JAVA = APP / "java" / "org" / "hakim" / "omega" / "companion"
POLICY = ROOT / "governance" / "HAKIM_RUNTIME_POLICY_v2.json"
PHONE_CONSTRAINTS = ROOT / "governance" / "HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json"
MANIFEST = APP / "AndroidManifest.xml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_financial_safe_mode_is_persistent_and_fail_closed():
    t = read(JAVA / "FinancialSafeMode.kt")
    assert 'const val KEY = "financial_safe_mode"' in t
    assert ".putBoolean(KEY, true)" in t
    assert "disableSelf()" in t
    assert "requestUnbind()" in t
    assert "stopService(Intent(context, HakimForegroundService::class.java))" in t


def test_financial_safe_mode_blocks_restart_paths():
    main = read(JAVA / "MainActivity.kt")
    boot = read(JAVA / "BootReceiver.kt")
    service = read(JAVA / "HakimForegroundService.kt")
    assert main.count("!FinancialSafeMode.isEnabled(this)") >= 3
    assert "if (FinancialSafeMode.isEnabled(context)) return" in boot
    assert "if (FinancialSafeMode.isEnabled(context)) return" in service
    assert "START_NOT_STICKY" in service


def test_notification_has_one_tap_financial_safe_mode_action():
    safe = read(JAVA / "FinancialSafeMode.kt")
    service = read(JAVA / "HakimForegroundService.kt")
    manifest = read(MANIFEST)
    assert 'ACTION_ENTER = "org.hakim.omega.companion.ENTER_FINANCIAL_SAFE_MODE"' in safe
    assert "class FinancialSafeModeReceiver : BroadcastReceiver()" in safe
    assert 'android:name=".FinancialSafeModeReceiver"' in manifest
    assert '"وضع مالي"' in service
    assert "FinancialSafeMode.ACTION_ENTER" in service


def test_normal_companion_control_does_not_require_developer_options_or_adb():
    all_text = "\n".join(read(path) for path in APP.rglob("*") if path.is_file() and path.suffix in {".kt", ".xml"})
    assert "WIRELESS_DEBUGGING_SETTINGS" not in all_text
    assert "APPLICATION_DEVELOPMENT_SETTINGS" not in all_text
    assert "adb pair" not in all_text.lower()
    assert "adb connect" not in all_text.lower()


def test_accessibility_control_remains_available_without_adb():
    t = read(JAVA / "HakimAccessibilityService.kt")
    assert "performGlobalAction" in t
    assert "dispatchGesture" in t
    assert "ACTION_SET_TEXT" in t
    assert "takeScreenshot" in t


def test_runtime_policy_uses_governing_local_adb_without_weakening_android_protection():
    p = json.loads(read(POLICY))
    control = p["device_control"]
    assert control["governing_phone_path"] == "TERMUX_WIRELESS_ADB_LOCAL"
    assert control["wireless_debugging_required_for_governing_local_path"] is True
    assert control["wireless_debugging_pairing"] == "ANDROID_LOCAL_PAIRING_REQUIRED_IF_NOT_ALREADY_TRUSTED"
    assert control["adb_policy"] == "LOCAL_GOVERNED_ALLOWLIST_ONLY_NO_GENERAL_REMOTE_SHELL"
    assert control["cloud_command_relay"] == "MAKE_PRIVATE_ON_DEMAND_RELAY"
    assert control["result_path"] == "RESULT_MAILBOX"
    assert control["financial_safe_mode"]["persistent_until_user_exit"] is True
    assert control["financial_safe_mode"]["disable_accessibility_service"] is True
    assert p["security"]["do_not_disable_platform_protection"] is True
    assert p["security"]["do_not_disable_play_protect"] is True
    assert p["security"]["no_general_remote_shell"] is True
    assert p["bridges"]["public_command_transport"] is False
    assert p["bridges"]["public_github_command_relay"] is False
    assert p["bridges"]["preferred"][0] == "TERMUX_WIRELESS_ADB_LOCAL"


def test_latest_user_phone_constraint_is_p0_and_not_overridable_by_generic_autonomy():
    c = json.loads(read(PHONE_CONSTRAINTS))
    assert c["priority"] == "P0"
    constraints = c["constraints"]
    assert constraints["governing_phone_path"] == "TERMUX_WIRELESS_ADB_LOCAL"
    assert constraints["cloud_command_relay"] == "MAKE_PRIVATE_ON_DEMAND_RELAY"
    assert constraints["result_path"] == "RESULT_MAILBOX"
    assert constraints["maintenance_bridge"] == "REMOTE_DESKTOP_COMMANDER_OPTIONAL_ONLY"
    assert constraints["public_command_transport"] == "FORBIDDEN"
    assert constraints["public_github_command_relay"] == "FORBIDDEN"
    assert constraints["general_remote_shell"] == "FORBIDDEN"
    assert constraints["play_protect_disable"] is False
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["optimization_cannot_override"] is True
    assert c["precedence"]["only_later_explicit_user_instruction_may_change"] is True
