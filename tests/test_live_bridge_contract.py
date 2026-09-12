from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_live_bridge_keeps_local_server_loopback_only():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt").read_text()
    assert 'const val LOOPBACK_HOST = "127.0.0.1"' in text
    assert "InetAddress.getByName(LOOPBACK_HOST)" in text
    assert "InetAddress.getLoopbackAddress()" not in text
    assert "0.0.0.0" not in text


def test_remote_relay_has_no_shell_surface_and_requires_approval_for_mutation():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt").read_text()
    assert 'setOf("status", "ui", "notifications", "screenshot")' in text
    assert 'setOf("action", "launch")' in text
    assert "showApproval(context, requestId, op)" in text
    assert "Runtime.getRuntime" not in text
    assert "ProcessBuilder" not in text
    assert "/bin/sh" not in text


def test_remote_relay_is_outbound_only_signed_and_replay_guarded():
    text = (ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt").read_text()
    assert "https://ntfy.sh/" in text
    assert "claimRemoteRequest" in text
    assert "request_expired" in text
    assert "HmacSHA256" in text
    assert "MessageDigest.isEqual" in text
    assert "validSignature" in text
    assert 'KEY_RELAY_KEY = "relay_hmac_key"' in text
    assert "ServerSocket" not in text


def test_remote_approval_receiver_not_exported():
    manifest = (ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml").read_text()
    marker = 'android:name=".RemoteApprovalReceiver"'
    i = manifest.index(marker)
    window = manifest[i : i + 180]
    assert 'android:exported="false"' in window


def test_live_bridge_shell_entrypoints_parse_and_chain_expected_scripts():
    configure = ROOT / "scripts/configure-hakim-live-bridge.sh"
    bootstrap = ROOT / "scripts/bootstrap-hakim-live-bridge.sh"
    for script in (configure, bootstrap):
        subprocess.run(["bash", "-n", str(script)], check=True)
    configure_text = configure.read_text()
    bootstrap_text = bootstrap.read_text()
    assert "relay_key" in configure_text
    assert "RELAY_KEY" in configure_text
    assert "install-android-companion-local.sh" in bootstrap_text
    assert "configure-hakim-live-bridge.sh" in bootstrap_text
    assert "RELAY_KEY" in bootstrap_text
    assert "git pull --ff-only" in bootstrap_text
