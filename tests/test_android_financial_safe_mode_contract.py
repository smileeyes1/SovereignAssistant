from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app" / "src" / "main"
JAVA = APP / "java" / "org" / "hakim" / "omega" / "companion"
POLICY = ROOT / "governance" / "HAKIM_RUNTIME_POLICY_v2.json"
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


def test_companion_path_itself_does_not_silently_enable_adb():
    all_text = "\n".join(read(path) for path in APP.rglob("*") if path.is_file() and path.suffix in {".kt", ".xml"})
    assert "WIRELESS_DEBUGGING_SETTINGS" not in all_text
    assert "APPLICATION_DEVELOPMENT_SETTINGS" not in all_text
    assert "adb pair" not in all_text.lower()
    assert "adb connect" not in all_text.lower()


def test_accessibility_component_remains_available_as_non_governing_component():
    t = read(JAVA / "HakimAccessibilityService.kt")
    assert "performGlobalAction" in t
    assert "dispatchGesture" in t
    assert "ACTION_SET_TEXT" in t
    assert "takeScreenshot" in t


def test_runtime_policy_locks_termux_wireless_adb_as_governing_field_path():
    p = json.loads(read(POLICY))
    control = p["device_control"]
    assert control["normal_phone_path"] == "TERMUX_WIRELESS_ADB_LOCAL"
    assert control["developer_options_required_for_normal_operation"] is True
    assert control["adb_policy"] == "PRIMARY_LOCAL_ALLOWLISTED_CONTROL_NO_GENERAL_REMOTE_SHELL"
    assert control["developer_options_policy"] == "LOCAL_USER_CONTROLLED_AND_REQUIRED_FOR_WIRELESS_ADB_PATH"
    assert control["financial_safe_mode"]["persistent_until_user_exit"] is True
    assert control["financial_safe_mode"]["disable_accessibility_service"] is True
    assert p["bridges"]["public_command_transport"] is False
    assert p["bridges"]["public_github_command_relay"] is False
    assert p["security"]["no_general_remote_shell"] is True
    assert p["security"]["do_not_disable_platform_protection"] is True
