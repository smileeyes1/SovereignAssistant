from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"


def test_local_control_server_remains_loopback_only():
    text = (JAVA / "LocalControlServer.kt").read_text(encoding="utf-8")
    assert "InetAddress.getLoopbackAddress()" in text
    assert "0.0.0.0" not in text


def test_background_remote_relay_source_is_removed_from_sovereign_local_runtime():
    assert not (JAVA / "HakimRemoteRelay.kt").exists()
    service = (JAVA / "HakimForegroundService.kt").read_text(encoding="utf-8")
    assert "HakimRemoteRelay" not in service
    assert 'putBoolean("external_transport_enabled", false)' in service
    assert "LocalControlServer" in service


def test_signed_task_surface_has_no_shell_and_is_expiring_replay_guarded():
    text = (JAVA / "HakimSignedTask.kt").read_text(encoding="utf-8")
    assert "Runtime.getRuntime" not in text
    assert "ProcessBuilder" not in text
    assert "/bin/sh" not in text
    assert 'Mac.getInstance("HmacSHA256")' in text
    assert "MessageDigest.isEqual" in text
    assert 'private const val MAX_FUTURE_MS' in text
    assert "task_duplicate" in text
    assert "ALLOWED_ACTIONS" in text


def test_manifest_has_no_remote_approval_receiver_or_sensitive_listener_services():
    manifest = (ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert "RemoteApprovalReceiver" not in manifest
    assert "BIND_ACCESSIBILITY_SERVICE" not in manifest
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in manifest
    assert 'android:host="task"' in manifest


def test_legacy_live_bridge_shell_entrypoints_are_syntactically_valid_and_fail_closed():
    configure = ROOT / "scripts/configure-hakim-live-bridge.sh"
    bootstrap = ROOT / "scripts/bootstrap-hakim-live-bridge.sh"
    for script in (configure, bootstrap):
        subprocess.run(["bash", "-n", str(script)], check=True)
        content = script.read_text(encoding="utf-8")
        assert "exit 64" in content
        assert "pair-android-companion.sh" in content
        assert "HAKIM_RELAY_TOPIC" not in content
        assert "HAKIM_RESULT_URL" not in content
        assert "HAKIM_RELAY_KEY" not in content
