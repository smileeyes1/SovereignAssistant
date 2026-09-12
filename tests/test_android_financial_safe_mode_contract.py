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


def test_financial_safe_mode_is_persistent_and_stops_local_control_fail_closed():
    t = read(JAVA / "FinancialSafeMode.kt")
    assert 'const val KEY = "financial_safe_mode"' in t
    assert ".putBoolean(KEY, true)" in t
    assert "stopService(Intent(context, HakimForegroundService::class.java))" in t
    assert 'prefs.getString("pair_token", null)' in t
    assert "HakimForegroundService.start(context)" in t


def test_financial_safe_mode_blocks_restart_paths():
    main = read(JAVA / "MainActivity.kt")
    boot = read(JAVA / "BootReceiver.kt")
    service = read(JAVA / "HakimForegroundService.kt")
    assert main.count("!FinancialSafeMode.isEnabled(this)") >= 2
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


def test_normal_companion_control_does_not_require_developer_options_adb_accessibility_or_notification_listener():
    all_text = "\n".join(read(path) for path in APP.rglob("*") if path.is_file() and path.suffix in {".kt", ".xml"})
    assert "WIRELESS_DEBUGGING_SETTINGS" not in all_text
    assert "APPLICATION_DEVELOPMENT_SETTINGS" not in all_text
    assert "adb pair" not in all_text.lower()
    assert "adb connect" not in all_text.lower()
    manifest = read(MANIFEST)
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in manifest
    assert not (JAVA / "HakimAccessibilityService.kt").exists()
    assert not (JAVA / "HakimNotificationListener.kt").exists()


def test_owned_browser_control_remains_available_without_adb():
    t = read(JAVA / "HakimBrowserController.kt")
    assert "WebView" in t
    assert "evaluateJavascript" in t
    assert "loadUrl" in t
    assert "loadDataWithBaseURL" in t
    assert '"local_proof"' in t


def test_runtime_policy_locks_sovereign_local_zero_relay_phone_control():
    p = json.loads(read(POLICY))
    control = p["device_control"]
    assert control["normal_phone_path"] == "SOVEREIGN_LOCAL_ANDROID_COMPANION_WITH_LOOPBACK_BROWSER_AND_USER_OPENED_SIGNED_TASK_LINK"
    assert control["developer_options_required_for_normal_operation"] is False
    assert control["wireless_debugging_required_for_normal_operation"] is False
    assert control["adb_policy"] == "TEMPORARY_MAINTENANCE_ONLY_AFTER_EXPLICIT_USER_REQUEST_THEN_OFF"
    assert control["developer_options_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert control["wireless_debugging_policy"] == "MUST_REMAIN_OFF_FOR_NORMAL_OPERATION"
    assert control["background_external_transport"] == "DISABLED_BY_DEFAULT"
    assert control["local_server_bind"] == "LOOPBACK_ONLY"
    assert control["financial_safe_mode"]["available"] is True
    bridges = p["bridges"]
    assert bridges["core_requires_bridge"] is False
    assert bridges["local_core_first"] is True
    assert "TERMUX_WIRELESS_ADB_EXPLICIT_TEMPORARY_MAINTENANCE_ONLY" in bridges["optional_non_core_only"]
    for forbidden in ("MAKE", "TINYFISH", "NTFY", "PAID_API", "PAID_OPERATION_CREDITS"):
        assert forbidden in bridges["forbidden_as_hidden_runtime_core"]


def test_latest_user_phone_constraint_is_p0_and_not_overridable_by_generic_autonomy():
    c = json.loads(read(PHONE_CONSTRAINTS))
    assert c["priority"] == "P0"
    constraints = c["constraints"]
    assert constraints["developer_options_normal_operation"] == "MUST_REMAIN_OFF"
    assert constraints["wireless_debugging_normal_operation"] == "MUST_REMAIN_OFF"
    assert constraints["normal_phone_path"] == "SOVEREIGN_LOCAL_ANDROID_COMPANION_WITH_LOOPBACK_BROWSER_AND_USER_OPENED_SIGNED_TASK_LINK"
    assert constraints["background_external_relay_normal_operation"] == "FORBIDDEN_BY_DEFAULT"
    assert constraints["make_runtime_dependency"] == "FORBIDDEN"
    assert constraints["tinyfish_runtime_dependency"] == "FORBIDDEN"
    assert constraints["ntfy_runtime_dependency"] == "FORBIDDEN"
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["optimization_cannot_override"] is True
    assert c["precedence"]["only_later_explicit_user_instruction_may_change"] is True
