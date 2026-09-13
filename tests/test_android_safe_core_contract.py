from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app"


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding="utf-8")


def test_safe_core_version_and_package_stay_update_compatible():
    gradle = read("build.gradle.kts")
    assert 'applicationId = "org.hakim.omega.companion"' in gradle
    assert 'versionCode = 20018' in gradle
    assert 'versionName = "0.5.0-canonical-phone-interface-native-adb"' in gradle


def test_safe_core_manifest_has_no_device_wide_sensitive_services():
    # الاسم التاريخي محفوظ للاستمرارية؛ العقد المطوّر يسمح فقط بخدمتي حكيم
    # المحددتين وبصلاحيات BIND النظامية التي لا يستطيع التطبيق منحها لنفسه.
    manifest = read("src/main/AndroidManifest.xml")
    assert 'android:name=".HakimAccessibilityService"' in manifest
    assert 'android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"' in manifest
    assert 'android:name=".HakimNotificationListener"' in manifest
    assert 'android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE"' in manifest
    assert manifest.count("BIND_ACCESSIBILITY_SERVICE") == 1
    assert manifest.count("BIND_NOTIFICATION_LISTENER_SERVICE") == 1
    # لا نضيف صلاحيات عامة حساسة أو قدرة إدارة ملفات/إعدادات آمنة.
    for forbidden in (
        "android.permission.QUERY_ALL_PACKAGES",
        "android.permission.MANAGE_EXTERNAL_STORAGE",
        "android.permission.WRITE_SECURE_SETTINGS",
        "android.permission.READ_SMS",
        "android.permission.SEND_SMS",
        "android.permission.READ_CONTACTS",
        "android.permission.RECORD_AUDIO",
        "android.permission.CAMERA",
        "android.permission.ACCESS_FINE_LOCATION",
    ):
        assert forbidden not in manifest
    config = read("src/main/res/xml/hakim_accessibility_service.xml")
    assert 'android:canRetrieveWindowContent="true"' in config
    assert 'android:canPerformGestures="true"' in config
    assert 'android:canTakeScreenshot="true"' in config


def test_safe_core_ui_does_not_invite_sensitive_settings():
    # الاسم التاريخي محفوظ؛ التفعيل الجديد مقصود أن يمر حصراً من شاشة أندرويد المحلية.
    activity = read("src/main/java/org/hakim/omega/companion/MainActivity.kt")
    assert "Settings.ACTION_ACCESSIBILITY_SETTINGS" in activity
    assert "Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS" in activity
    assert 'button("تفعيل التحكم بالجهاز")' in activity
    assert 'button("تفعيل قراءة الإشعارات")' in activity
    assert "HakimAccessibilityService.instance != null" in activity
    assert "HakimNotificationListener.isConnected()" in activity
    # لا يوجد منح صامت عبر WRITE_SECURE_SETTINGS أو أوامر settings secure.
    assert "WRITE_SECURE_SETTINGS" not in activity
    assert "enabled_accessibility_services" not in activity


def test_compatibility_routes_are_confined_to_owned_browser():
    # مسارات التوافق القديمة تبقى متصفح حكيم فقط؛ قدرات الجهاز لها namespace مستقل.
    server = read("src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert '"safe_core", true' in server
    assert '(path == "/v1/ui" || path == "/v1/browser/ui")' in server
    assert '(path == "/v1/screenshot" || path == "/v1/browser/screenshot")' in server
    assert '(path == "/v1/action" || path == "/v1/browser/action")' in server
    assert '"scope", "OWNED_BROWSER_ONLY"' in server
    assert 'path == "/v1/device/ui"' in server
    assert 'path == "/v1/device/screenshot"' in server
    assert 'path == "/v1/device/action"' in server
    assert 'path == "/v1/notifications"' in server
    assert "HakimAccessibilityService.instance" in server
    assert "HakimNotificationListener.isConnected()" in server
    assert "FinancialSafeMode.isEnabled(context)" in server
    assert "InetAddress.getLoopbackAddress()" in server
    assert 'headers["authorization"] != "Bearer $token"' in server
    assert '!claimRequest("device:$requestId")' in server
