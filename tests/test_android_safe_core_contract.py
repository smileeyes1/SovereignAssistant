from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app"


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding="utf-8")


def test_safe_core_version_and_package_stay_update_compatible():
    gradle = read("build.gradle.kts")
    assert 'applicationId = "org.hakim.omega.companion"' in gradle
    assert 'versionCode = 20018' in gradle
    assert 'versionName = "0.4.3-native-local-adb-bootstrap"' in gradle


def test_safe_core_manifest_has_no_device_wide_sensitive_services():
    manifest = read("src/main/AndroidManifest.xml")
    assert "HakimAccessibilityService" not in manifest
    assert "HakimNotificationListener" not in manifest
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in manifest
    assert ".HakimForegroundService" in manifest
    assert 'android.permission.INTERNET' in manifest


def test_safe_core_ui_does_not_invite_sensitive_settings():
    activity = read("src/main/java/org/hakim/omega/companion/MainActivity.kt")
    assert "ACTION_ACCESSIBILITY_SETTINGS" not in activity
    assert "ACTION_NOTIFICATION_LISTENER_SETTINGS" not in activity
    assert "تحكم الواجهة" not in activity
    assert "وصول الإشعارات" not in activity
    assert "نطاق التحكم الحالي المثبت: متصفح حكيم المملوك" in activity
    assert "التحكم الأوسع لا يُدّعى قبل التأهيل الميداني" in activity


def test_compatibility_routes_are_confined_to_owned_browser():
    server = read("src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert '"safe_core", true' in server
    assert '"control_scope", "OWNED_BROWSER_ONLY"' in server
    assert '(path == "/v1/ui" || path == "/v1/browser/ui")' in server
    assert '(path == "/v1/screenshot" || path == "/v1/browser/screenshot")' in server
    assert '(path == "/v1/action" || path == "/v1/browser/action")' in server
    assert '"notification_access_not_registered"' in server
    assert "HakimAccessibilityService" not in server
    assert "HakimNotificationListener" not in server
