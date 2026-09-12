from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "android/hakim-companion/app/src/main"
LEGACY_RELAY = SRC / "java/org/hakim/omega/companion/HakimRemoteRelay.kt"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def all_runtime_text():
    chunks = []
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix in {".kt", ".xml", ".java"}:
            chunks.append(p.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_runtime_has_no_external_background_transport_dependency():
    runtime = all_runtime_text()
    forbidden = ["ntfy.sh", "hook.eu1.make.com", "TinyFish", "HakimRemoteRelay("]
    for marker in forbidden:
        assert marker not in runtime


def test_legacy_relay_source_is_physically_absent_from_release_tree():
    assert not LEGACY_RELAY.exists()
    service = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimForegroundService.kt")
    assert "HakimRemoteRelay" not in service
    assert "LocalControlServer" in service
    assert 'putBoolean("external_transport_enabled", false)' in service


def test_local_control_is_loopback_only():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert "InetAddress.getLoopbackAddress()" in server
    assert '.put("loopback_only", true)' in server


def test_signed_task_channel_is_local_expiring_and_replay_protected():
    task = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimSignedTask.kt")
    assert 'uri.scheme != "hakim" || uri.host != "task"' in task
    assert 'Mac.getInstance("HmacSHA256")' in task
    assert 'private const val MAX_FUTURE_MS' in task
    assert "task_duplicate" in task
    assert 'getSharedPreferences("hakim_signed_task_ids"' in task
    assert "HakimBrowserController.action(step)" in task


def test_offline_local_proof_exists_for_field_verification_without_external_carrier():
    browser = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimBrowserController.kt")
    task = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimSignedTask.kt")
    assert '"local_proof" -> showLocalProof' in browser
    assert 'loadDataWithBaseURL("https://hakim.local/"' in browser
    assert "دون ناقل خارجي أو طلب شبكة" in browser
    assert '"local_proof"' in task


def test_manifest_exposes_only_pair_and_signed_task_links_not_remote_receiver():
    manifest = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'android:host="pair"' in manifest
    assert 'android:host="task"' in manifest
    assert "RemoteApprovalReceiver" not in manifest
    assert "AccessibilityService" not in manifest
    assert "NotificationListenerService" not in manifest


def test_version_is_sovereign_local_release():
    gradle = text("android/hakim-companion/app/build.gradle.kts")
    assert "versionCode = 5" in gradle
    assert 'versionName = "0.4.0-sovereign-local"' in gradle
