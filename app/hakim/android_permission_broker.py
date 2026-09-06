"""Local Android approval broker for HAKIM Ω.

Prefers Termux:API notifications as the human-sovereign gate. When that backend
cannot be used, a loopback-only browser gate is the bootstrap fallback. Approval
state remains local; no cloud account, ChatGPT memory, or remote service is
required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
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
    """One-time, expiring local approval requests."""

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

    def notification_gate_proven(self) -> bool:
        """Return PASS only after a real notification-channel human decision."""
        if not self.audit_path.is_file():
            return False
        try:
            for line in self.audit_path.read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                if row.get('event') in {'approval.approved', 'approval.rejected'} and row.get('channel') == 'notification':
                    return True
        except Exception:
            return False
        return False

    def notifications_available(self) -> bool:
        """Compatibility name: means field-qualified notification gate, not package presence."""
        return self.notification_gate_proven()

    @staticmethod
    def browser_fallback_available() -> bool:
        return shutil.which('am') is not None

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
            'ui_channel': None,
            'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        }
        _atomic_json(self._path(request_id), doc)
        self._audit('approval.requested', {'request_id': request_id, 'action': action, 'risk': risk})
        if notify:
            self._notify(doc, token)
        return request_id, token

    def _set_channel(self, request_id: str, channel: str) -> dict[str, Any]:
        doc = self._load(request_id)
        doc['ui_channel'] = channel
        _atomic_json(self._path(request_id), doc)
        return doc

    def _notify(self, doc: dict[str, Any], token: str) -> None:
        # Never query Android package manager here. On some Android/Termux builds
        # package-service Binder queries themselves fail even while local runtime
        # is healthy. The backend is judged by the actual notification command.
        if shutil.which('termux-notification') is None and not self.notifications_available():
            raise RuntimeError('termux-notification CLI is unavailable')
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
        self._set_channel(rid, 'notification')
        self._audit('approval.notified', {'request_id': rid, 'notification_id': nid, 'channel': 'notification'})

    def _start_browser_gate(self, doc: dict[str, Any], token: str) -> ThreadingHTTPServer:
        if not self.browser_fallback_available():
            raise RuntimeError('local browser approval fallback is unavailable')
        broker = self
        rid = str(doc['request_id'])
        self._set_channel(rid, 'browser')
        nonce = secrets.token_urlsafe(32)
        page_path = f'/approval/{nonce}'
        approve_path = f'{page_path}/approved'
        reject_path = f'{page_path}/rejected'
        title = html.escape('HAKIM Ω — طلب إذن')
        summary = html.escape(str(doc['summary']))
        risk = html.escape(str(doc['risk']))

        class Handler(BaseHTTPRequestHandler):
            server_version = 'HAKIMLocalGate/1'

            def _headers(self, status: int = 200, content_type: str = 'text/html; charset=utf-8') -> None:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header(
                    'Content-Security-Policy',
                    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
                )
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()

            def do_GET(self) -> None:
                if self.path != page_path:
                    self._headers(404)
                    self.wfile.write(b'Not found')
                    return
                body = f"""<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font-family:sans-serif;max-width:42rem;margin:2rem auto;padding:1rem;line-height:1.7}}
.card{{border:1px solid #777;border-radius:16px;padding:1.25rem}}
button{{font-size:1.2rem;padding:.8rem 1.4rem;margin:.5rem;border-radius:12px}}
</style></head><body><div class="card"><h1>{title}</h1>
<p>{summary}</p><p><strong>المخاطر:</strong> {risk}</p>
<form method="post" action="{approve_path}"><button type="submit">سماح</button></form>
<form method="post" action="{reject_path}"><button type="submit">رفض</button></form>
<p>هذه الصفحة محلية على الهاتف فقط، وتنتهي صلاحيتها تلقائيًا.</p>
</div></body></html>"""
                self._headers(200)
                self.wfile.write(body.encode('utf-8'))

            def do_POST(self) -> None:
                if self.path == approve_path:
                    decision = 'approved'
                elif self.path == reject_path:
                    decision = 'rejected'
                else:
                    self._headers(404)
                    self.wfile.write(b'Not found')
                    return
                try:
                    result = broker.decide(rid, token, decision)
                except Exception:
                    self._headers(409)
                    self.wfile.write('تعذر تسجيل القرار.'.encode('utf-8'))
                    return
                self._headers(200)
                label = 'تم السماح.' if result.status == 'approved' else 'تم الرفض.'
                self.wfile.write(
                    f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">'
                    f'<h2>{html.escape(label)}</h2><p>يمكنك إغلاق هذه الصفحة.</p></html>'.encode('utf-8')
                )
                threading.Thread(target=self.server.shutdown, daemon=True).start()

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name=f'hakim-gate-{rid[:8]}', daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        if host != '127.0.0.1':
            server.shutdown(); server.server_close()
            raise RuntimeError('browser gate refused non-loopback bind')
        url = f'http://127.0.0.1:{port}{page_path}'
        proc = self.runner(
            ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url],
            text=True,
            capture_output=True,
            timeout=10,
            shell=False,
        )
        if getattr(proc, 'returncode', 0) != 0:
            server.shutdown(); server.server_close()
            raise RuntimeError(f"failed to open local approval page: {getattr(proc, 'stderr', '')}")
        self._audit('approval.browser_fallback_opened', {'request_id': rid, 'bind': '127.0.0.1', 'channel': 'browser'})
        return server

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
            self._audit('approval.expired', {'request_id': request_id, 'channel': doc.get('ui_channel')})
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
            self._audit('approval.invalid_token', {'request_id': request_id, 'channel': doc.get('ui_channel')})
            raise PermissionError('invalid approval token')
        doc = self._load(request_id)
        doc['status'] = decision
        doc['decided_at'] = self.clock().isoformat()
        _atomic_json(self._path(request_id), doc)
        channel = doc.get('ui_channel')
        self._audit(f'approval.{decision}', {'request_id': request_id, 'action': doc['action'], 'channel': channel})
        if channel == 'notification' and shutil.which('termux-notification-remove'):
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
        request_id, token = self.request(action, summary, risk=risk, ttl_seconds=ttl_seconds, notify=False)
        server: ThreadingHTTPServer | None = None
        notification_error: Exception | None = None
        try:
            if shutil.which('termux-notification') is not None or self.notifications_available():
                try:
                    self._notify(self._load(request_id), token)
                except Exception as exc:
                    notification_error = exc
                    self._audit(
                        'approval.notification_backend_failed',
                        {'request_id': request_id, 'error': str(exc)[:300]},
                    )
            if self._load(request_id).get('ui_channel') != 'notification':
                if self.browser_fallback_available():
                    server = self._start_browser_gate(self._load(request_id), token)
                else:
                    self._audit('approval.no_local_ui', {'request_id': request_id})
                    if notification_error is not None:
                        raise RuntimeError('notification backend failed; falling back to local browser gate was unavailable') from notification_error
                    raise RuntimeError('no local human-approval UI is available')
            while True:
                d = self.decision(request_id)
                if d.status in self.FINAL:
                    return d
                time.sleep(max(0.1, poll_seconds))
        finally:
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                server.server_close()


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
