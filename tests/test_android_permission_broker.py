from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess

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
    # Final decisions are immutable; a later denial cannot rewrite approval.
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
