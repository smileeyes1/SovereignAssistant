from pathlib import Path


def test_repair_helper_preserves_measured_gate_and_user_consent():
    s = Path('scripts/repair-tecno-background.sh').read_text(encoding='utf-8')
    assert 'REQUEST_IGNORE_BATTERY_OPTIMIZATIONS' in s
    assert 'APPLICATION_DETAILS_SETTINGS' in s
    assert 'com.transsion.phonemaster' in s
    assert 'com.transsion.batterylab' in s
    assert 'Auto-start' in s
    assert 'Unrestricted' in s
    assert 'termux-wake-lock' in s
    assert 'background-test start --seconds 300 --interval 5' in s
    assert 'background-test status' in s
    assert 'read -r' in s


def test_repair_helper_does_not_fake_or_bypass_result():
    s = Path('scripts/repair-tecno-background.sh').read_text(encoding='utf-8')
    lowered = s.lower()
    assert 'status":"pass"' not in lowered
    assert 'adb shell' not in lowered
    assert 'cmd appops set' not in lowered
    assert 'deviceidle whitelist +' not in lowered
    assert 'curl ' not in lowered
    assert 'wget ' not in lowered
