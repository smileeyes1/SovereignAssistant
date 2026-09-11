from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_bridge_keeps_local_server_loopback_only():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt").read_text()
    assert "InetAddress.getLoopbackAddress()" in text
    assert "0.0.0.0" not in text


def test_remote_relay_has_no_shell_surface_and_requires_approval_for_mutation():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt").read_text()
    assert 'setOf("status", "ui", "notifications", "screenshot")' in text
    assert 'setOf("action", "launch")' in text
    assert "showApproval(context, requestId, op)" in text
    assert "Runtime.getRuntime" not in text
    assert "ProcessBuilder" not in text
    assert "/bin/sh" not in text


def test_remote_relay_is_outbound_only_and_replay_guarded():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt").read_text()
    assert "https://ntfy.sh/" in text
    assert "https://" in text
    assert "claimRemoteRequest" in text
    assert "request_expired" in text
    assert "ServerSocket" not in text


def test_remote_approval_receiver_not_exported():
    manifest = (ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml").read_text()
    marker = 'android:name=".RemoteApprovalReceiver"'
    i = manifest.index(marker)
    window = manifest[i : i + 180]
    assert 'android:exported="false"' in window
