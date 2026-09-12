from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_supervisor_reconnects_local_adb_without_starting_public_worker():
    s = text("scripts/hakim-multibridge-supervisor.sh")
    assert "adb mdns services" in s
    assert "adb connect" in s
    assert "hakim-multibridge-state.json" in s
    assert "LEGACY_PUBLIC_WORKER_SESSION=\"hakim-relay-worker\"" in s
    assert "legacy_public_relay_worker_stopped_by_policy" in s
    assert "tmux kill-session -t \"$LEGACY_PUBLIC_WORKER_SESSION\"" in s
    assert "tmux new-session -d" not in s


def test_supervisor_state_matches_sovereign_bridge_policy():
    s = text("scripts/hakim-multibridge-supervisor.sh")
    assert "'public_command_transport':'disabled_by_sovereign_policy'" in s
    assert "'public_github_command_relay':'disabled'" in s
    assert "'legacy_public_relay_worker':'stopped'" in s
    assert "'make_private_command_relay':'required_unproven'" in s
    assert "'remote_desktop_commander':'optional_maintenance_only'" in s
    assert "'result_mailbox':'configured_result_path'" in s
    assert "'github_relay':'configured'" not in s
    assert "'make_relay':'fallback-configured'" not in s


def test_bootstrap_installs_supervisor_status_and_private_transport_only():
    s = text("scripts/bootstrap-hakim-termux-adb.sh")
    assert "hakim-multibridge-supervisor" in s
    assert "hakim-bridges-status" in s
    assert ".termux/boot/99-hakim-multibridge" in s
    assert "upstream_bridges" in s
    assert "make-private-relay" in s
    assert "fallback_bridges':[]" in s
    assert "public_command_transport':False" in s
    assert "github-owner-relay" not in s
    assert "make-fallback" not in s
    assert "remote-desktop-commander" in s


def test_mutating_control_is_fail_closed_by_default():
    boot = text("scripts/bootstrap-hakim-termux-adb.sh")
    pair = text("scripts/hakim-adb-pair.sh")
    assert "hakim-control-window\" 60" not in boot
    assert "hakim-control-window\" 60" not in pair
    assert "hakim-control-on 15" in pair


def test_no_security_bypass_or_remote_shell_added():
    all_text = "\n".join([
        text("scripts/hakim-multibridge-supervisor.sh"),
        text("scripts/bootstrap-hakim-termux-adb.sh"),
        text("scripts/hakim-adb-pair.sh"),
    ]).lower()
    for forbidden in ("disable play protect", "settings put global verifier_verify_adb_installs 0", "adb shell sh -c", "remote shell"):
        assert forbidden not in all_text
