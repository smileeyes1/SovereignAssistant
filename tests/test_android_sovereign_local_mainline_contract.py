from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "android/hakim-companion/app/src/main"
JAVA = SRC / "java/org/hakim/omega/companion"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def runtime_text():
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in SRC.rglob("*")
        if p.is_file() and p.suffix in {".kt", ".xml", ".java"}
    )


def test_privileged_and_external_runtime_components_are_physically_absent():
    for name in [
        "HakimAccessibilityService.kt",
        "HakimNotificationListener.kt",
        "HakimRemoteRelay.kt",
        "HakimDirectRelay.kt",
    ]:
        assert not (JAVA / name).exists()
    assert not (SRC / "res/xml/accessibility_service_config.xml").exists()


def test_runtime_has_no_named_external_background_transport_dependency():
    runtime = runtime_text()
    for marker in ["ntfy.sh", "hook.eu1.make.com", "TinyFish", "HakimRemoteRelay", "HakimDirectRelay"]:
        assert marker not in runtime


def test_loopback_local_control_and_signed_task_are_present():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    task = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimSignedTask.kt")
    assert "InetAddress.getLoopbackAddress()" in server
    assert '.put("external_transport_enabled", false)' in server
    assert 'uri.scheme != "hakim" || uri.host != "task"' in task
    assert 'Mac.getInstance("HmacSHA256")' in task
    assert "task_duplicate" in task
    assert "MAX_FUTURE_MS" in task


def test_manifest_has_only_local_core_and_explicit_deep_links():
    manifest = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'android:host="pair"' in manifest
    assert 'android:host="task"' in manifest
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in manifest
    assert "RemoteApprovalReceiver" not in manifest
    assert "DirectApprovalReceiver" not in manifest


def test_release_version_and_no_false_field_claim():
    gradle = text("android/hakim-companion/app/build.gradle.kts")
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert "versionCode = 7" in gradle
    assert 'versionName = "0.4.2-sovereign-local"' in gradle
    assert '.put("evidence_state", "NOT_PROVEN")' in server
