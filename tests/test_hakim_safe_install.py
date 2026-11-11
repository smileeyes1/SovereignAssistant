from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFE_MANIFEST = ROOT / "android/hakim-companion/app/src/safe/AndroidManifest.xml"
SAFE_ACTIVITY = ROOT / "android/hakim-companion/app/src/safe/java/org/hakim/omega/companion/SafeMainActivity.kt"
GRADLE = ROOT / "android/hakim-companion/app/build.gradle.kts"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_safe_build_type_is_separate_and_identity_stays_canonical():
    s = read(GRADLE)
    assert 'create("safe")' in s
    assert 'applicationId = "org.hakim.omega.companion"' in s
    assert 'versionCode = 20018' in s
    assert 'signingConfig = signingConfigs.getByName("debug")' in s


def test_safe_manifest_removes_sensitive_capabilities():
    s = read(SAFE_MANIFEST)
    for permission in [
        "android.permission.RECEIVE_BOOT_COMPLETED",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
        "android.permission.WAKE_LOCK",
    ]:
        assert permission in s
    for component in [
        ".HakimForegroundService",
        ".HakimAccessibilityService",
        ".HakimNotificationListener",
        ".BootReceiver",
    ]:
        assert component in s
    assert s.count('tools:node="remove"') >= 10
    assert '.SafeMainActivity' in s


def test_safe_activity_is_browser_only_and_never_calls_sensitive_services():
    s = read(SAFE_ACTIVITY)
    assert "HakimBrowserController.attach" in s
    assert "HakimBrowserController.openChatGpt" in s
    assert "HakimBrowserController.installGovernanceHooks" in s
    assert "HakimForegroundService" not in s
    assert "HakimAccessibilityService" not in s
    assert "HakimNotificationListener" not in s
    assert "ACTION_ACCESSIBILITY_SETTINGS" not in s
    assert "ACTION_NOTIFICATION_LISTENER_SETTINGS" not in s
    assert "HakimLocalPairing" not in s
