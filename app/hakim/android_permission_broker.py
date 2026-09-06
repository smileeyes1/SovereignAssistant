"""Local Android approval broker for HAKIM Ω.

Uses Termux:API notifications as a human-sovereign gate. Approval state is
stored locally; no cloud account, ChatGPT memory, or remote service is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Callable
import uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    status: str
    action: str
    summary: str
    risk: str
    created_at: str
    expires_at: str
    decided_at: str | None = None


class AndroidPermissionBroker:
    """One-time, expiring approval requests surfaced as Android notifications."""

    FINAL = {'approved', 'rejected', 'expired'}

    def __init__(
        self,
        root: str | Path,
        *,
        clock: Callable[[], datetime] = _utcnow,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.root = Path(root).expanduser().resolve()
        self.dir = self.root / '.omega' / 'approvals'
        self.dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.dir / 'audit.jsonl'
        self.clock = clock
        self.runner = runner

    @staticmethod
    def notifications_available() -> bool:
        return shutil.which('termux-notification') is not None

    def _path(self, request_id: str) -> Path:
        if not request_id or any(c not in '0123456789abcdef-' for c in request_id.lower()):
            raise ValueError('invalid request id')
        return self.dir / f'{request_id}.json'

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        row = {'at': self.clock().isoformat(), 'event': event, **payload}
        with self.audit_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        os.chmod(self.audit_path, 0o600)

    def request(
        self,
        action: str,
        summary: str,
        *,
        risk: str = 'high',
        ttl_seconds: int = 300,
        notify: bool = True,
    ) -> tuple[str, str]:
        action = action.strip()[:160]
        summary = summary.strip()[:500]
        risk = risk.strip()[:40] or 'high'
        if not action or not summary:
            raise ValueError('action and summary are required')
        if not 15 <= ttl_seconds <= 3600:
            raise ValueError('ttl_seconds must be between 15 and 3600')
        request_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        now = self.clock()
        doc = {
            'request_id': request_id,
            'action': action,
            'summary': summary,
            'risk': risk,
            'created_at': now.isoformat(),
            'expires_at': (now + timedelta(seconds=ttl_seconds)).isoformat(),
            'status': 'pending',
            'decided_at': None,
            'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        }
        _atomic_json(self._path(request_id), doc)
        self._audit('approval.requested', {'request_id': request_id, 'action': action, 'risk': risk})
        if notify:
            self._notify(doc, token)
        return request_id, token

    def _notify(self, doc: dict[str, Any], token: str) -> None:
        if not self.notifications_available():
            raise RuntimeError('termux-notification is unavailable; install Termux:API app and pkg termux-api')
        script = str(Path(__file__).resolve())
        py = sys.executable or 'python3'
        root = str(self.root)
        rid = str(doc['request_id'])
        base = [py, script, '--root', root, 'decide', '--request-id', rid, '--token', token]
        allow = ' '.join(shlex.quote(x) for x in [*base, '--decision', 'approved'])
        deny = ' '.join(shlex.quote(x) for x in [*base, '--decision', 'rejected'])
        nid = str(int(uuid.UUID(rid)) % 2_000_000_000)
        argv = [
            'termux-notification', '--id', nid,
            '--title', 'HAKIM Ω — طلب إذن',
            '--content', f"{doc['summary']}  |  المخاطر: {doc['risk']}",
            '--priority', 'high', '--sound',
            '--button1', 'سماح', '--button1-action', allow,
            '--button2', 'رفض', '--button2-action', deny,
        ]
        proc = self.runner(argv, text=True, capture_output=True, timeout=15, shell=False)
        if getattr(proc, 'returncode', 0) != 0:
            raise RuntimeError(f"notification failed: {getattr(proc, 'stderr', '')}")
        self._audit('approval.notified', {'request_id': rid, 'notification_id': nid})

    def _load(self, request_id: str) -> dict[str, Any]:
        path = self._path(request_id)
        if not path.is_file():
            raise KeyError(request_id)
        doc = json.loads(path.read_text(encoding='utf-8'))
        if doc.get('request_id') != request_id:
            raise ValueError('approval record identity mismatch')
        return doc

    def decision(self, request_id: str) -> ApprovalDecision:
        doc = self._load(request_id)
        if doc['status'] == 'pending' and self.clock() >= datetime.fromisoformat(doc['expires_at']):
            doc['status'] = 'expired'
            doc['decided_at'] = self.clock().isoformat()
            _atomic_json(self._path(request_id), doc)
            self._audit('approval.expired', {'request_id': request_id})
        return ApprovalDecision(
            request_id=request_id, status=doc['status'], action=doc['action'], summary=doc['summary'],
            risk=doc['risk'], created_at=doc['created_at'], expires_at=doc['expires_at'], decided_at=doc.get('decided_at'),
        )

    def decide(self, request_id: str, token: str, decision: str) -> ApprovalDecision:
        if decision not in {'approved', 'rejected'}:
            raise ValueError('decision must be approved or rejected')
        doc = self._load(request_id)
        current = self.decision(request_id)
        if current.status in self.FINAL:
            return current
        expected = str(doc['token_sha256'])
        actual = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(expected, actual):
            self._audit('approval.invalid_token', {'request_id': request_id})
            raise PermissionError('invalid approval token')
        doc = self._load(request_id)
        doc['status'] = decision
        doc['decided_at'] = self.clock().isoformat()
        _atomic_json(self._path(request_id), doc)
        self._audit(f'approval.{decision}', {'request_id': request_id, 'action': doc['action']})
        if shutil.which('termux-notification-remove'):
            nid = str(int(uuid.UUID(request_id)) % 2_000_000_000)
            try:
                self.runner(['termux-notification-remove', nid], text=True, capture_output=True, timeout=10, shell=False)
            except Exception:
                pass
        return self.decision(request_id)

    def request_and_wait(
        self,
        action: str,
        summary: str,
        *,
        risk: str = 'high',
        ttl_seconds: int = 300,
        poll_seconds: float = 0.5,
    ) -> ApprovalDecision:
        request_id, _token = self.request(action, summary, risk=risk, ttl_seconds=ttl_seconds, notify=True)
        while True:
            d = self.decision(request_id)
            if d.status in self.FINAL:
                return d
            time.sleep(max(0.1, poll_seconds))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog='omega-android-approval')
    parser.add_argument('--root', default='~/hakim-workspace')
    sub = parser.add_subparsers(dest='cmd', required=True)
    req = sub.add_parser('request')
    req.add_argument('--action', required=True); req.add_argument('--summary', required=True)
    req.add_argument('--risk', default='high'); req.add_argument('--ttl', type=int, default=300)
    req.add_argument('--wait', action='store_true')
    dec = sub.add_parser('decide')
    dec.add_argument('--request-id', required=True); dec.add_argument('--token', required=True)
    dec.add_argument('--decision', choices=['approved', 'rejected'], required=True)
    get = sub.add_parser('status'); get.add_argument('--request-id', required=True)
    args = parser.parse_args()
    broker = AndroidPermissionBroker(args.root)
    if args.cmd == 'request':
        if args.wait:
            result = broker.request_and_wait(args.action, args.summary, risk=args.risk, ttl_seconds=args.ttl)
            print(json.dumps(result.__dict__, ensure_ascii=False))
        else:
            rid, _ = broker.request(args.action, args.summary, risk=args.risk, ttl_seconds=args.ttl)
            print(json.dumps({'request_id': rid, 'status': 'pending'}, ensure_ascii=False))
    elif args.cmd == 'decide':
        print(json.dumps(broker.decide(args.request_id, args.token, args.decision).__dict__, ensure_ascii=False))
    else:
        print(json.dumps(broker.decision(args.request_id).__dict__, ensure_ascii=False))


if __name__ == '__main__':
    main()
