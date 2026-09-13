from pathlib import Path

P = Path('scripts/hakim-multibridge-supervisor.sh')


def text():
    return P.read_text(encoding='utf-8')


def test_saved_target_reconnect_precedes_mdns():
    s = text()
    a = s.index("adb connect \"$target\"")
    b = s.index('discover_target_mdns')
    assert a > b  # function definition appears earlier
    loop = s.index('while true; do')
    a2 = s.index("adb connect \"$target\"", loop)
    b2 = s.index('found="$(discover_target_mdns)"', loop)
    assert a2 < b2


def test_result_channel_is_outbound_only_and_optional():
    s = text()
    assert 'Result telemetry is OUTBOUND ONLY' in s
    assert "[[ \"$url\" =~ ^https:// ]] || return 0" in s
    assert "curl -fsS -m 5" in s
    assert "result_telemetry_failed" in s


def test_no_pairing_secret_is_sent():
    s = text()
    payload = s[s.index("payload=\"") : s.index("# The historical relay worker")]
    for forbidden in ['PAIR_CODE', 'pairing_code', 'password', 'storepass', 'keypass', 'token']:
        assert forbidden not in payload


def test_public_command_transport_remains_disabled():
    s = text()
    assert "d['public_command_transport']=False" in s
    assert "'public_github_command_relay':'disabled'" in s
    assert "stop_legacy_public_worker" in s
