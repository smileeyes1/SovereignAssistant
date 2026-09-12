from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"


def test_live_bridge_keeps_local_server_loopback_only():
    text = (APP / "LocalControlServer.kt").read_text(encoding="utf-8")
    assert "InetAddress.getLoopbackAddress()" in text
    assert "0.0.0.0" not in text


def test_signed_task_has_no_shell_surface_and_is_allowlisted():
    text = (APP / "HakimSignedTask.kt").read_text(encoding="utf-8")
    assert "ALLOWED_ACTIONS" in text
    assert '"local_proof"' in text
    assert '"click_css"' in text
    assert '"set_text"' in text
    assert "Runtime.getRuntime" not in text
    assert "ProcessBuilder" not in text
    assert "/bin/sh" not in text
    assert "task_bad_signature" in text
    assert "task_duplicate" in text
    assert "task_expired_or_too_far" in text


def test_external_relay_sources_and_receivers_are_absent():
    assert not (APP / "HakimRemoteRelay.kt").exists()
    assert not (APP / "HakimDirectRelay.kt").exists()
    manifest = (ROOT / "android/hakim-companion/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert "RemoteApprovalReceiver" not in manifest
    assert "DirectApprovalReceiver" not in manifest
    assert 'android:host="task"' in manifest


def test_legacy_live_bridge_shell_entrypoints_parse_but_fail_closed():
    configure = ROOT / "scripts/configure-hakim-live-bridge.sh"
    bootstrap = ROOT / "scripts/bootstrap-hakim-live-bridge.sh"
    for script in (configure, bootstrap):
        subprocess.run(["bash", "-n", str(script)], check=True)
        body = script.read_text(encoding="utf-8")
        assert "exit 64" in body
        assert "relay_key" not in body.lower()
        assert "ntfy" not in body.lower()
    assert "pair-android-companion.sh" in configure.read_text(encoding="utf-8")
    assert "install-android-companion-local.sh" in bootstrap.read_text(encoding="utf-8")
