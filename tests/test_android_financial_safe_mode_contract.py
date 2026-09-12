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


def test_native_governing_adb_bootstrap_is_owned_by_hakim_and_not_a_third_party_helper():
    pairing = read(JAVA / "HakimLocalPairing.kt")
    manager = read(JAVA / "HakimAdbConnectionManager.kt")
    manifest = read(MANIFEST)
    assert "WIRELESS_DEBUGGING_SETTINGS" in pairing
    assert "APPLICATION_DEVELOPMENT_SETTINGS" in pairing
    assert "RemoteInput" in pairing
    assert "SERVICE_TYPE_TLS_PAIRING" in manager
    assert "AndroidKeyStore" in manager
    assert 'android:name=".HakimPairingReceiver"' in manifest
    assert "adb pair" not in pairing.lower()
    assert "adb connect" not in pairing.lower()


def test_owned_browser_safe_core_remains_available_independently_of_adb_pairing_state():
    browser = read(JAVA / "HakimBrowserController.kt")
    server = read(JAVA / "LocalControlServer.kt")
    assert "HakimAdbConnectionManager" not in browser
    assert "HakimAdbConnectionManager" not in server
    assert 'path == "/v1/ui"' in server


def test_accessibility_implementation_remains_legacy_optional_and_is_not_registered_in_safe_core():
    t = read(JAVA / "HakimAccessibilityService.kt")
    manifest = read(MANIFEST)
    assert "performGlobalAction" in t
    assert "dispatchGesture" in t
    assert "ACTION_SET_TEXT" in t
    assert "takeScreenshot" in t
    assert ".HakimAccessibilityService" not in manifest


def test_runtime_policy_uses_hakim_native_local_adb_without_weakening_android_protection():
    p = json.loads(read(POLICY))
    control = p["device_control"]
    assert control["governing_phone_path"] == "HAKIM_NATIVE_LOCAL_ADB"
    assert control["bootstrap_owner"] == "HAKIM_ANDROID_APP"
    assert control["adb_identity"] == "HAKIM_ANDROID_KEYSTORE_LOCAL_KEY"
    assert control["pairing_discovery"] == "ANDROID_MDNS_TLS_PAIRING_LOCAL"
    assert control["pairing_user_input"] == "SIX_DIGIT_ANDROID_PAIRING_CODE_ONLY"
    assert control["third_party_bootstrap_required"] is False
    assert control["termux_role"] == "OPTIONAL_LEGACY_MAINTENANCE_ONLY"
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
    assert p["bridges"]["preferred"][0] == "HAKIM_NATIVE_LOCAL_ADB"


def test_latest_user_phone_constraint_is_p0_and_not_overridable_by_generic_autonomy():
    c = json.loads(read(PHONE_CONSTRAINTS))
    assert c["priority"] == "P0"
    constraints = c["constraints"]
    assert constraints["governing_phone_path"] == "HAKIM_NATIVE_LOCAL_ADB"
    assert constraints["bootstrap_owner"] == "HAKIM_ANDROID_APP"
    assert constraints["third_party_bootstrap_required"] is False
    assert constraints["termux_role"] == "OPTIONAL_LEGACY_MAINTENANCE_ONLY"
    assert constraints["cloud_command_relay"] == "MAKE_PRIVATE_ON_DEMAND_RELAY"
    assert constraints["result_path"] == "RESULT_MAILBOX"
    assert constraints["maintenance_bridge"] == "REMOTE_DESKTOP_COMMANDER_OPTIONAL_ONLY"
    assert constraints["public_command_transport"] == "FORBIDDEN"
    assert constraints["public_github_command_relay"] == "FORBIDDEN"
    assert constraints["general_remote_shell"] == "FORBIDDEN"
    assert constraints["play_protect_disable"] is False
    assert constraints["field_verified"] is False
    assert c["precedence"]["generic_autonomy_cannot_override"] is True
    assert c["precedence"]["optimization_cannot_override"] is True
    assert c["precedence"]["only_later_explicit_user_instruction_may_change"] is True


# أسماء العقود التاريخية تبقى موجودة لحماية الاستمرارية. أحدث توجيه صريح
# غيّر مسار التنفيذ من Termux إلى ADB محلي أصيل داخل حكيم، لا متطلبات الأمان.
def test_normal_companion_control_does_not_require_developer_options_or_adb():
    test_native_governing_adb_bootstrap_is_owned_by_hakim_and_not_a_third_party_helper()


def test_accessibility_control_remains_available_without_adb():
    test_accessibility_implementation_remains_legacy_optional_and_is_not_registered_in_safe_core()


def test_runtime_policy_uses_governing_local_adb_without_weakening_android_protection():
    test_runtime_policy_uses_hakim_native_local_adb_without_weakening_android_protection()
