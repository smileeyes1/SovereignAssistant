from pathlib import Path

P = Path('scripts/hakim-local-adb-recover.py')


def s():
    return P.read_text(encoding='utf-8')


def test_recovery_prefers_existing_pairing_paths_before_scan():
    t = s()
    assert t.index('adb_online(saved) or connect(saved)') < t.index('for target in mdns_targets()')
    assert t.index('for target in mdns_targets()') < t.index('for port in listening_ports()')
    assert t.index('for port in listening_ports()') < t.index('for port in scan_ports(ip)')


def test_scan_is_bounded_and_only_high_ports():
    t = s()
    assert 'range(20000, 60001)' in t
    assert 'max_workers=320' in t


def test_success_persists_target_and_restarts_supervisor():
    t = s()
    assert 'd["adb_target"] = target' in t
    assert 'restart_supervisor()' in t
    assert 'HAKIM_LOCAL_ADB_RECOVER=PASS' in t


def test_recovery_never_pairs_or_carries_pairing_secrets():
    t = s().lower()
    for forbidden in ['adb pair', 'pair_code', 'pairing_code', 'storepass', 'keypass']:
        assert forbidden not in t


def test_public_command_transport_remains_disabled():
    t = s()
    assert 'd["public_command_transport"] = False' in t
