from datetime import datetime, timedelta, timezone
import json
import subprocess
import urllib.request

import pytest

from app.hakim.android_permission_broker import AndroidPermissionBroker


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 6, 3, 30, tzinfo=timezone.utc)
    def __call__(self):
        return self.now


class Runner:
    def __init__(self):
        self.calls = []
    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '', '')


def test_approval_is_one_time_and_token_bound(tmp_path):
    clock = Clock(); runner = Runner()
    broker = AndroidPermissionBroker(tmp_path, clock=clock, runner=runner)
    rid, token = broker.request('publish', 'Publish release', ttl_seconds=60, notify=False)
    assert broker.decision(rid).status == 'pending'
    with pytest.raises(PermissionError):
        broker.decide(rid, 'wrong-token', 'approved')
    assert broker.decision(rid).status == 'pending'
    assert broker.decide(rid, token, 'approved').status == 'approved'
    assert broker.decide(rid, token, 'rejected').status == 'approved'


def test_request_expires_without_human_decision(tmp_path):
    clock = Clock()
    broker = AndroidPermissionBroker(tmp_path, clock=clock)
    rid, _ = broker.request('delete', 'Delete protected artifact', ttl_seconds=15, notify=False)
    clock.now += timedelta(seconds=16)
    assert broker.decision(rid).status == 'expired'


def test_notification_has_only_fixed_approve_reject_actions(tmp_path, monkeypatch):
    clock = Clock(); runner = Runner()
    broker = AndroidPermissionBroker(tmp_path, clock=clock, runner=runner)
    monkeypatch.setattr(broker, 'notifications_available', lambda: True)
    rid, _ = broker.request('external-write', 'Send controlled external write', ttl_seconds=60, notify=True)
    argv, kwargs = runner.calls[-1]
    assert argv[0] == 'termux-notification'
    assert '--button1' in argv and 'سماح' in argv
    assert '--button2' in argv and 'رفض' in argv
    assert '--button1-action' in argv and '--button2-action' in argv
    assert kwargs['shell'] is False
    assert rid not in ''.join(argv[:1])


def test_notification_gate_requires_real_notification_channel_decision(tmp_path, monkeypatch):
    runner = Runner()
    broker = AndroidPermissionBroker(tmp_path, runner=runner)
    monkeypatch.setattr(broker, 'notifications_available', lambda: True)
    rid, token = broker.request('field-test', 'Notification field proof', ttl_seconds=60, notify=True)
    assert broker.notification_gate_proven() is False
    assert broker.decide(rid, token, 'approved').status == 'approved'
    assert broker.notification_gate_proven() is True
    assert not any(call[0][:2] == ['pm', 'path'] for call in runner.calls)


def test_browser_fallback_binds_loopback_and_records_decision(tmp_path, monkeypatch):
    runner = Runner()
    broker = AndroidPermissionBroker(tmp_path, runner=runner)
    monkeypatch.setattr(broker, 'browser_fallback_available', lambda: True)
    rid, token = broker.request('test', 'Local fallback', ttl_seconds=60, notify=False)
    server = broker._start_browser_gate(broker._load(rid), token)
    try:
        argv, kwargs = runner.calls[-1]
        assert argv[:5] == ['am', 'start', '-a', 'android.intent.action.VIEW', '-d']
        assert kwargs['shell'] is False
        url = argv[-1]
        assert url.startswith('http://127.0.0.1:')
        with urllib.request.urlopen(url, timeout=3) as response:
            page = response.read().decode('utf-8')
        assert 'سماح' in page and 'رفض' in page
        assert 'http://' not in page and 'https://' not in page
        approve_url = url + '/approved'
        request = urllib.request.Request(approve_url, data=b'', method='POST')
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
        assert broker.decision(rid).status == 'approved'
        assert broker.notification_gate_proven() is False
    finally:
        server.shutdown()
        server.server_close()


def test_records_are_private_and_audited(tmp_path):
    broker = AndroidPermissionBroker(tmp_path)
    rid, token = broker.request('privacy', 'Read protected local data', ttl_seconds=60, notify=False)
    p = tmp_path / '.omega' / 'approvals' / f'{rid}.json'
    doc = json.loads(p.read_text(encoding='utf-8'))
    assert token not in p.read_text(encoding='utf-8')
    assert len(doc['token_sha256']) == 64
    assert (tmp_path / '.omega' / 'approvals' / 'audit.jsonl').is_file()


def test_invalid_ttl_and_empty_fields_are_rejected(tmp_path):
    broker = AndroidPermissionBroker(tmp_path)
    with pytest.raises(ValueError): broker.request('', 'summary', notify=False)
    with pytest.raises(ValueError): broker.request('action', '', notify=False)
    with pytest.raises(ValueError): broker.request('action', 'summary', ttl_seconds=5, notify=False)
