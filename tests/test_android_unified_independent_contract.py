from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
MANIFEST = ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml"
GRADLE = ROOT / "android/hakim-companion/app/build.gradle.kts"


def text(path):
    return Path(path).read_text(encoding="utf-8")


def test_direct_transport_is_zero_cost_encrypted_and_result_topic_based():
    relay = text(APP / "HakimDirectRelay.kt")
    assert 'const val KEY_RESULT_TOPIC = "relay_result_topic"' in relay
    assert 'const val KEY_RELAY_BASE = "relay_base_url"' in relay
    assert 'private const val DEFAULT_RELAY_BASE = "https://ntfy.sh"' in relay
    assert 'private const val CARRIER_PREFIX = "HC1."' in relay
    assert 'private const val RESULT_PREFIX = "HR1."' in relay
    assert 'AES/GCM/NoPadding' in relay
    assert 'Mac.getInstance("HmacSHA256")' in relay
    assert 'duplicate_request' in relay
    assert 'request_expired' in relay
    assert 'DirectApprovalReceiver' in relay
    assert 'hook.eu1.make.com' not in relay
    assert 'relay_result_url' not in relay


def test_foreground_runtime_uses_direct_transport_not_legacy_transport():
    service = text(APP / "HakimForegroundService.kt")
    assert 'HakimDirectRelay' in service
    assert 'HakimRemoteRelay(' not in service
    assert 'START_STICKY' in service


def test_safe_unified_build_keeps_owned_browser_without_sensitive_device_services():
    manifest = text(MANIFEST)
    activity = text(APP / "MainActivity.kt")
    local = text(APP / "LocalControlServer.kt")
    assert '.HakimAccessibilityService' not in manifest
    assert '.HakimNotificationListener' not in manifest
    assert 'BIND_ACCESSIBILITY_SERVICE' not in manifest
    assert 'BIND_NOTIFICATION_LISTENER_SERVICE' not in manifest
    assert '.DirectApprovalReceiver' in manifest
    assert 'HakimBrowserController.attach(browser)' in activity
    assert 'Settings.ACTION_ACCESSIBILITY_SETTINGS' not in activity
    assert 'Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS' not in activity
    assert 'HakimDirectRelay.configure' in activity
    assert 'HakimAccessibilityService.instance' not in local
    assert 'HakimNotificationListener.isConnected()' not in local
    assert 'HakimBrowserController.uiSnapshot()' in local
    assert 'HakimBrowserController.screenshotBase64()' in local
    assert '"control_scope", "OWNED_BROWSER_ONLY"' in local


def test_pairing_survives_update_key_names_and_release_version_moves_forward():
    activity = text(APP / "MainActivity.kt")
    relay = text(APP / "HakimDirectRelay.kt")
    gradle = text(GRADLE)
    assert 'uri.getQueryParameter("result_topic")' in activity
    assert 'uri.getQueryParameter("relay_base")' in activity
    assert 'const val KEY_TOPIC = "relay_topic"' in relay
    assert 'const val KEY_RELAY_KEY = "relay_hmac_key"' in relay
    assert 'versionCode = 6' in gradle
    assert 'versionName = "0.4.1-safe-browser-core"' in gradle


def test_financial_safe_mode_remains_a_runtime_gate():
    service = text(APP / "HakimForegroundService.kt")
    activity = text(APP / "MainActivity.kt")
    assert 'FinancialSafeMode.isEnabled' in service
    assert 'FinancialSafeMode.enter(this)' in activity
    assert 'FinancialSafeMode.exit(this)' in activity
