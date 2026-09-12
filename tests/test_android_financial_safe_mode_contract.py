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
    assert 'putString("companion_mode", "FINANCIAL_SAFE")' in t
    assert "stopService(Intent(context, HakimForegroundService::class.java))" in t
    assert "HakimAccessibilityService" not in t
    assert "HakimNotificationListener" not in t


def test_financial_safe_mode_blocks_restart_paths():
    main = read(JAVA / "MainActivity.kt")
    boot = read(JAVA / "BootReceiver.kt")
    service = read(JAVA / "HakimForegroundService.kt")
    assert main.count("!FinancialSafeMode.isEnabled(this)") >= 2
    assert "if (FinancialSafeMode.isEnabled(context)) return" in boot
    assert "if (FinancialSafeMode.isEnabled(context)) return" in service
    assert "START_NOT_STICKY" in service
    assert 'if (!prefs.getString("pair_token", null).isNullOrBlank())' in read(JAVA / "FinancialSafeMode.kt")


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


def test_owned_browser_control_remains_available_without_adb_or_privileged_services():
    browser = read(JAVA / "HakimBrowserController.kt")
    manifest = read(MANIFEST)
    assert "evaluateJavascript" in browser
    assert "loadDataWithBaseURL" in browser
    assert "click_css" in browser
    assert "set_text" in browser
    assert "screenshotBase64" in browser
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in manifest


def test_runtime_policy_locks_no_developer_options_for_normal_phone_control():
    p = json.loads(read(POLICY))
    control = p["device_control"]
    assert control["normal_phone_path"] == "ANDROID_COMPANION_SOVEREIGN_LOCAL_OWNED_BROWSER"
    assert control["developer_options_required_for_normal_operation"] is False
    assert control["wireless_debugging_required_for_normal_operation"] is False
    assert control["accessibility_service_required_for_normal_operation"] is False
    assert control["notification_listener_required_for_normal_operation"] is False
    assert control["external_background_command_transport"] is False
    assert control["adb_policy"] == "TEMPORARY_MAINTENANCE_ONLY_AFTER_EXPLICIT_USER_REQUEST_THEN_OFF"
    assert control["developer_options_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert control["wireless_debugging_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert control["financial_safe_mode"]["persistent_until_user_exit"] is True
    assert control["financial_safe_mode"]["stop_local_control_service"] is True
    assert p["bridges"]["public_command_transport"] is False
    assert p["bridges"]["external_background_command_transport"] is False
    assert "TERMUX_WIRELESS_ADB" not in p["bridges"]["preferred"]
    assert "TERMUX_WIRELESS_ADB" in p["bridges"]["maintenance_only"]


def test_latest_user_phone_constraint_is_p0_and_not_overridable_by_generic_autonomy():
    c = json.loads(read(PHONE_CONSTRAINTS))
    assert c["priority"] == "P0"
    assert c["constraints"]["developer_options_normal_operation"] == "MUST_REMAIN_OFF"
    assert c["constraints"]["wireless_debugging_normal_operation"] == "MUST_REMAIN_OFF"
    assert c["constraints"]["normal_phone_path"] == "ANDROID_COMPANION_SOVEREIGN_LOCAL_OWNED_BROWSER"
    assert c["constraints"]["external_background_command_transport"] == "FORBIDDEN_IN_NORMAL_OPERATION"
    assert c["constraints"]["accessibility_service_required"] is False
    assert c["constraints"]["notification_listener_required"] is False
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["optimization_cannot_override"] is True
    assert c["precedence"]["only_later_explicit_user_instruction_may_change"] is True
