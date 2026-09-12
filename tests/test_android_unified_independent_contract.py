from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
MANIFEST = ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml"
GRADLE = ROOT / "android/hakim-companion/app/build.gradle.kts"


def text(path):
    return Path(path).read_text(encoding="utf-8")


def test_normal_runtime_has_no_external_background_transport():
    for name in ["HakimDirectRelay.kt", "HakimRemoteRelay.kt"]:
        assert not (APP / name).exists()
    service = text(APP / "HakimForegroundService.kt")
    local = text(APP / "LocalControlServer.kt")
    assert "HakimDirectRelay" not in service
    assert "HakimRemoteRelay" not in service
    assert 'putBoolean("external_transport_enabled", false)' in service
    assert '.put("external_transport_enabled", false)' in local


def test_foreground_runtime_uses_loopback_local_control():
    service = text(APP / "HakimForegroundService.kt")
    local = text(APP / "LocalControlServer.kt")
    assert 'LocalControlServer(this@HakimForegroundService)' in service
    assert 'InetAddress.getLoopbackAddress()' in local
    assert 'START_STICKY' in service


def test_sovereign_build_keeps_owned_browser_and_removes_privileged_device_services():
    manifest = text(MANIFEST)
    activity = text(APP / "MainActivity.kt")
    local = text(APP / "LocalControlServer.kt")
    assert '.HakimAccessibilityService' not in manifest
    assert '.HakimNotificationListener' not in manifest
    assert '.DirectApprovalReceiver' not in manifest
    assert '.RemoteApprovalReceiver' not in manifest
    assert 'HakimBrowserController.attach(browser)' in activity
    assert 'HakimAccessibilityService' not in activity
    assert 'HakimNotificationListener' not in activity
    assert 'HakimBrowserController.uiSnapshot()' in local
    assert 'HakimBrowserController.screenshotBase64()' in local


def test_pairing_survives_update_and_release_version_moves_forward():
    activity = text(APP / "MainActivity.kt")
    gradle = text(GRADLE)
    assert 'uri.getQueryParameter("token")' in activity
    assert 'putString("pair_token", token)' in activity
    assert 'putString("pair_mode", "SOVEREIGN_LOCAL")' in activity
    assert 'versionCode = 6' in gradle
    assert 'versionName = "0.5.0-sovereign-local-mainline"' in gradle


def test_signed_local_task_channel_is_authenticated_expiring_and_replay_guarded():
    task = text(APP / "HakimSignedTask.kt")
    assert 'uri.scheme != "hakim" || uri.host != "task"' in task
    assert 'Mac.getInstance("HmacSHA256")' in task
    assert 'MessageDigest.isEqual' in task
    assert 'MAX_FUTURE_MS' in task
    assert 'task_bad_signature' in task
    assert 'task_duplicate' in task
    assert 'task_expired_or_too_far' in task
    assert 'ALLOWED_ACTIONS' in task


def test_financial_safe_mode_remains_a_runtime_gate():
    service = text(APP / "HakimForegroundService.kt")
    activity = text(APP / "MainActivity.kt")
    assert 'FinancialSafeMode.isEnabled' in service
    assert 'FinancialSafeMode.enter(this)' in activity
    assert 'FinancialSafeMode.exit(this)' in activity
