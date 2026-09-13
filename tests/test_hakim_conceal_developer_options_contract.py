from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'hakim-conceal-developer-options.sh'
GUARD = ROOT / 'scripts' / 'hakim-dev-mode-guardian.sh'
BOOT = ROOT / 'scripts' / 'hakim-zero-burden-bootstrap.sh'
SUP = ROOT / 'scripts' / 'hakim-multibridge-supervisor.sh'


def test_conceal_path_changes_only_master_visibility_after_wireless_is_proven():
    s = SCRIPT.read_text(encoding='utf-8')
    assert 'WIRELESS_ADB_NOT_ENABLED' in s
    assert 'settings put global development_settings_enabled 0' in s
    assert 'adb_wifi_enabled' in s
    assert 'DEV_AFTER' in s and 'WIFI_AFTER' in s
    assert 'FIELD_VERIFIED_DEV_MASTER_OFF_WIRELESS_ADB_ON=PASS' in s


def test_conceal_path_has_detached_rollback_before_mutation():
    s = SCRIPT.read_text(encoding='utf-8')
    rollback = s.index('sleep 40')
    mutation = s.index('settings put global development_settings_enabled 0')
    assert rollback < mutation
    assert "settings put global development_settings_enabled '$DEV_BEFORE'" in s
    assert "settings put global adb_wifi_enabled '$WIFI_BEFORE'" in s
    assert "rm -f '$REMOTE_FLAG'" in s


def test_guardian_is_proven_by_self_healing_master_flag():
    s = SCRIPT.read_text(encoding='utf-8')
    g = GUARD.read_text(encoding='utf-8')
    assert 'start_guardian' in s and 'guardian_running' in s
    assert 'DEV_MASTER_GUARD_SELF_HEAL=PASS' in s
    assert 'settings put global development_settings_enabled 1' in s
    assert 'settings put global development_settings_enabled 0' in g
    assert 'settings put global adb_wifi_enabled 1' in g


def test_bootstrap_exposes_one_command_and_boot_retry_only_after_field_pass():
    s = BOOT.read_text(encoding='utf-8')
    assert 'conceal-dev)' in s
    assert 'reveal-dev)' in s
    assert 'hakim-conceal-dev-options' in s
    assert 'developer_master_off_wireless_adb_on_field_verified' in s
    assert 'hakim-boot-conceal.log' in s


def test_supervisor_restarts_guardian_only_after_field_verification():
    s = SUP.read_text(encoding='utf-8')
    assert 'developer_master_off_wireless_adb_on_field_verified' in s
    assert 'ensure_dev_guardian' in s
    assert 'hakim-dev-mode-guardian.sh' in s
    assert 'dev_guardian_restarted' in s
