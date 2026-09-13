from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'hakim-conceal-developer-options.sh'
BOOT = ROOT / 'scripts' / 'hakim-zero-burden-bootstrap.sh'


def test_conceal_path_changes_only_master_visibility_after_wireless_is_proven():
    s = SCRIPT.read_text(encoding='utf-8')
    assert 'WIRELESS_ADB_NOT_ENABLED' in s
    assert 'settings put global development_settings_enabled 0' in s
    assert "adb_wifi_enabled" in s
    assert "DEV_AFTER" in s and "WIFI_AFTER" in s
    assert 'FIELD_VERIFIED_DEV_OPTIONS_CONCEALED_WITH_WIRELESS_ADB=PASS' in s


def test_conceal_path_has_detached_rollback_before_mutation():
    s = SCRIPT.read_text(encoding='utf-8')
    rollback = s.index("sleep 18")
    mutation = s.index('settings put global development_settings_enabled 0')
    assert rollback < mutation
    assert "settings put global development_settings_enabled '$DEV_BEFORE'" in s
    assert "settings put global adb_wifi_enabled '$WIFI_BEFORE'" in s
    assert 'conceal_developer_options_field_verified' in s


def test_bootstrap_exposes_one_command_and_boot_retry_only_after_field_pass():
    s = BOOT.read_text(encoding='utf-8')
    assert 'conceal-dev)' in s
    assert 'hakim-conceal-dev-options' in s
    assert 'conceal_developer_options_field_verified' in s
    assert 'hakim-boot-conceal.log' in s
