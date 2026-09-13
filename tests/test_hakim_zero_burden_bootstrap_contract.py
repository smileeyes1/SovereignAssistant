from pathlib import Path

P = Path('scripts/hakim-zero-burden-bootstrap.sh')


def s():
    return P.read_text(encoding='utf-8')


def test_one_command_bootstrap_preserves_existing_config():
    t = s()
    assert 'if [[ ! -f "$CFG" ]]' in t
    assert 'without overwriting any established result URL/target' in t


def test_bootstrap_uses_ff_only_update_and_never_resets_user_repo():
    t = s()
    assert 'git -C "$ROOT" pull --ff-only origin main' in t
    assert 'reset --hard' not in t
    assert 'git clean' not in t


def test_bootstrap_reuses_existing_pairing_before_interactive_fallback():
    t = s()
    assert 'TARGET="$(wait_online 20 || true)"' in t
    assert "exec \"$ROOT/scripts/bootstrap-hakim-termux-adb.sh\"" in t


def test_bootstrap_runs_reconnect_regression():
    t = s()
    assert 'adb disconnect "$TARGET"' in t
    assert 'RECONNECT_AFTER_DISCONNECT=PASS' in t
    assert 'adb kill-server' in t
    assert 'RECONNECT_AFTER_KILL_SERVER=PASS' in t
    assert 'FIELD_VERIFIED_LOCAL_ADB_RECONNECT=PASS' in t


def test_bootstrap_does_not_uninstall_or_clear_apps():
    t = s()
    for forbidden in ['pm clear', 'uninstall', 'rm -rf /data/user', 'adb install']:
        assert forbidden not in t
