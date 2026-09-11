from pathlib import Path
import ast
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "hakim-termux-adb-bridge.py"
BOOT = ROOT / "scripts" / "bootstrap-hakim-termux-adb.sh"
PAIR = ROOT / "scripts" / "hakim-adb-pair.sh"
CONTROL = ROOT / "scripts" / "hakim-control-window.sh"
SUPERVISOR = ROOT / "scripts" / "hakim-multibridge-supervisor.sh"
STATUS = ROOT / "scripts" / "hakim-bridges-status.sh"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bridge_python_parses():
    ast.parse(read(BRIDGE))


def test_shell_helpers_parse():
    for path in (BOOT, PAIR, CONTROL, SUPERVISOR, STATUS):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_bridge_keeps_signed_replay_safe_protocol():
    t = read(BRIDGE)
    assert "HmacSHA256" not in t
    assert "hmac.new" in t
    assert "compare_digest" in t
    assert "expires_at_ms" in t
    assert "hakim-termux-seen.json" in t
    assert 'ALLOWED = {"status", "ui", "screenshot", "notifications", "action", "launch"}' in t


def test_bridge_has_no_arbitrary_remote_shell():
    t = read(BRIDGE)
    assert '"shell"' not in t.split("ALLOWED =", 1)[0]
    assert 'op == "shell"' not in t
    assert 'subprocess.run(cmd' in t
    assert 'shell=True' not in t
    assert 'os.system' not in t
    assert 'eval(' not in t


def test_mutations_require_local_control_window():
    t = read(BRIDGE)
    assert "local_control_window_closed" in t
    assert t.count("if not control_window_open()") >= 2
    c = read(CONTROL)
    assert "0..1440" in c
    assert "hakim-control-until" in c


def test_bootstrap_uses_official_wireless_adb_and_no_apk():
    t = read(BOOT)
    s = read(SUPERVISOR)
    assert "android-tools" in t
    assert "adb mdns services" in s
    assert "WIRELESS_DEBUGGING_SETTINGS" in t
    assert "apk_required':False" in t
    assert "install-android-companion-local.sh" not in t
    assert "Play Protect" in t
    assert "hakim-multibridge-supervisor" in t


def test_bootstrap_pins_private_command_transport_and_disables_public_fallback():
    t = read(BOOT)
    assert "'upstream_bridges':['make-private-relay']" in t
    assert "'fallback_bridges':[]" in t
    assert "'public_command_transport':False" in t
    assert "github-owner-relay" not in t


def test_pairing_is_local_and_hands_lifecycle_to_supervisor():
    t = read(PAIR)
    assert "adb pair" in t
    assert "adb connect" in t
    assert "tmux new-session -d -s hakim-multibridge-supervisor" in t
    assert "hakim-control-on 15" in t
    assert "hakim-control-window\" 60" not in t
    assert "PAIR_CODE" in t
