"""Android/Termux runner for HAKIM Ω with local human approval gates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from .android_permission_broker import AndroidPermissionBroker
from .local_sovereign import (
    GuardedWorkspace,
    LocalAgentLoop,
    LocalModelClient,
    LocalSovereignConfig,
    LocalSovereignStore,
    VerifiedBackupManager,
)


class PermissionAwareWorkspace(GuardedWorkspace):
    def __init__(self, root, store, broker: AndroidPermissionBroker):
        super().__init__(root, store)
        self.broker = broker

    def dispatch(self, tool, args):
        if tool == 'request_approval':
            result = self.broker.request_and_wait(
                str(args.get('action', 'consequential-action')),
                str(args.get('summary', 'يحتاج HAKIM Ω موافقتك قبل تنفيذ هذا الفعل.')),
                risk=str(args.get('risk', 'high')),
                ttl_seconds=int(args.get('ttl_seconds', 300)),
            )
            return result.__dict__
        return super().dispatch(tool, args)


class AndroidAgentLoop(LocalAgentLoop):
    SYSTEM = """You are HAKIM Ω Android sovereign agent. Work only toward the user's stated goal.
Preserve verified success. Use reversible local tools autonomously. For any consequential or irreversible action,
DO NOT execute it directly: call request_approval and continue only if status=approved.
Return exactly one JSON object per turn, no Markdown. Either:
{"action":"tool","tool":"list_dir|read_text|search_text|write_text|mkdir|sha256|run_process|request_approval","args":{...},"reason":"..."}
or {"action":"final","status":"PASS|CONDITIONAL_PASS|NOT_PROVEN|FAIL|NO_GO|BLOCKED","message":"..."}.
Never invent approval, tool results, or device state. Rejection/expiry is authoritative. Remote/cloud access is optional, never required for runtime identity."""


class AndroidSovereignRuntime:
    def __init__(self, config: LocalSovereignConfig):
        self.config = config
        self.config.root.mkdir(parents=True, exist_ok=True)
        self.store = LocalSovereignStore(config.db_path)
        self.broker = AndroidPermissionBroker(config.root)
        self.workspace = PermissionAwareWorkspace(config.root, self.store, self.broker)
        self.backups = VerifiedBackupManager(self.store, config.backup_dir)
        self.model = LocalModelClient(config.model, base_url=config.model_base_url) if config.model.strip() else None

    def doctor(self):
        db_ok = self.config.db_path.exists() and self.config.db_path.parent.is_dir()
        model_configured = self.model is not None
        model_healthy = self.model.health() if self.model is not None else False
        notification_gate = self.broker.notification_gate_proven()
        browser_ok = self.broker.browser_fallback_available()
        if notification_gate:
            human_gate = 'PASS'
        elif browser_ok:
            human_gate = 'DEGRADED_LOCAL_FALLBACK'
        else:
            human_gate = 'FAIL'
        return {
            'runtime': 'PASS' if db_ok else 'FAIL',
            'state_db': 'PASS' if db_ok else 'FAIL',
            'notifications': 'PASS' if notification_gate else 'NOT_PROVEN',
            'notification_gate': 'PASS' if notification_gate else 'NOT_PROVEN',
            'local_browser_gate': 'PASS' if browser_ok else 'NOT_CONFIGURED',
            'human_gate': human_gate,
            'model': 'PASS' if model_healthy else ('NOT_PROVEN' if model_configured else 'NOT_CONFIGURED'),
            'last_verified_checkpoint': self.store.last_verified_checkpoint_id(),
            'queue': self.store.queue_counts(),
        }


def _approval_security_self_test(broker: AndroidPermissionBroker) -> dict:
    request_id, real_token = broker.request(
        'approval-security-self-test',
        'اختبار داخلي: الرمز الخاطئ يجب ألا يمنح موافقة.',
        risk='test',
        ttl_seconds=60,
        notify=False,
    )
    before = broker.decision(request_id).status
    wrong_token_rejected = False
    try:
        broker.decide(request_id, 'HAKIM-intentionally-wrong-token', 'approved')
    except PermissionError:
        wrong_token_rejected = True
    after_wrong = broker.decision(request_id).status
    final = broker.decide(request_id, real_token, 'rejected').status
    passed = wrong_token_rejected and before == 'pending' and after_wrong == 'pending' and final == 'rejected'
    return {
        'status': 'PASS' if passed else 'FAIL',
        'request_id': request_id,
        'wrong_token_rejected': wrong_token_rejected,
        'state_before': before,
        'state_after_wrong_token': after_wrong,
        'cleanup_final_status': final,
        'token_exposed': False,
    }


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _background_worker(root: str, test_id: str, seconds: int, interval: int) -> None:
    base = Path(root).expanduser().resolve() / '.omega' / 'background-tests'
    base.mkdir(parents=True, exist_ok=True)
    state_path = base / f'{test_id}.json'
    heartbeat_path = base / f'{test_id}.jsonl'
    started = time.time()
    deadline = started + seconds
    count = 0
    while True:
        now = time.time()
        count += 1
        with heartbeat_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'at': now, 'n': count}, sort_keys=True) + '\n')
        _atomic_json(state_path, {
            'test_id': test_id,
            'status': 'running',
            'pid': os.getpid(),
            'started_at': started,
            'expected_end_at': deadline,
            'seconds': seconds,
            'interval': interval,
            'heartbeat_count': count,
            'last_heartbeat_at': now,
        })
        if now >= deadline:
            break
        time.sleep(min(interval, max(0.1, deadline - now)))
    completed = time.time()
    _atomic_json(state_path, {
        'test_id': test_id,
        'status': 'completed',
        'pid': os.getpid(),
        'started_at': started,
        'expected_end_at': deadline,
        'completed_at': completed,
        'seconds': seconds,
        'interval': interval,
        'heartbeat_count': count,
        'last_heartbeat_at': completed,
    })


def _background_test_evaluate(state: dict, beats: list[float], *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    seconds = int(state.get('seconds', 0))
    interval = int(state.get('interval', 0))
    started = float(state.get('started_at', 0))
    expected_end = float(state.get('expected_end_at', started + seconds))
    if state.get('status') != 'completed':
        if now <= expected_end + max(15, interval * 3):
            return {'status': 'IN_PROGRESS', 'test_id': state.get('test_id'), 'heartbeat_count': len(beats)}
        return {
            'status': 'FAIL',
            'test_id': state.get('test_id'),
            'reason': 'background worker did not complete within grace window',
            'heartbeat_count': len(beats),
        }
    if len(beats) < 2 or seconds <= 0 or interval <= 0:
        return {'status': 'FAIL', 'test_id': state.get('test_id'), 'reason': 'insufficient heartbeat evidence'}
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    observed = beats[-1] - beats[0]
    max_gap = max(gaps) if gaps else 0.0
    minimum_beats = max(2, int((seconds / interval) * 0.75))
    passed = (
        observed >= max(0, seconds - interval * 2)
        and max_gap <= max(30, interval * 4)
        and len(beats) >= minimum_beats
    )
    return {
        'status': 'PASS' if passed else 'FAIL',
        'test_id': state.get('test_id'),
        'seconds_requested': seconds,
        'heartbeat_count': len(beats),
        'minimum_heartbeat_count': minimum_beats,
        'observed_span_seconds': round(observed, 3),
        'max_gap_seconds': round(max_gap, 3),
        'wake_lock_expected': True,
        'scope': 'Termux process survival under user-initiated background/screen-off test',
    }


def _background_test_start(root: Path, seconds: int, interval: int) -> dict:
    if not 60 <= seconds <= 3600:
        raise ValueError('seconds must be between 60 and 3600')
    if not 2 <= interval <= 30:
        raise ValueError('interval must be between 2 and 30')
    base = root / '.omega' / 'background-tests'
    base.mkdir(parents=True, exist_ok=True)
    test_id = str(uuid.uuid4())
    (base / 'latest').write_text(test_id + '\n', encoding='utf-8')
    wake_lock_requested = False
    if shutil.which('termux-wake-lock'):
        proc = subprocess.run(['termux-wake-lock'], text=True, capture_output=True, timeout=10, shell=False)
        wake_lock_requested = proc.returncode == 0
    code = (
        'from app.hakim.run_android_sovereign import _background_worker; '
        '_background_worker(*__import__("sys").argv[1:3], '
        'int(__import__("sys").argv[3]), int(__import__("sys").argv[4]))'
    )
    proc = subprocess.Popen(
        [sys.executable, '-c', code, str(root), test_id, str(seconds), str(interval)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=(base / f'{test_id}.stderr.log').open('ab'),
        start_new_session=True,
    )
    time.sleep(0.25)
    return {
        'status': 'STARTED',
        'test_id': test_id,
        'pid': proc.pid,
        'seconds': seconds,
        'interval': interval,
        'wake_lock_requested': wake_lock_requested,
        'physical_step_required': 'ضع Termux على Unrestricted إن كان HiOS يعرض الخيار، ثم اخرج من Termux وأطفئ الشاشة طوال مدة الاختبار.',
        'check_command': 'hakim-android background-test status',
    }


def _background_test_status(root: Path) -> dict:
    base = root / '.omega' / 'background-tests'
    latest = base / 'latest'
    if not latest.is_file():
        return {'status': 'NOT_PROVEN', 'reason': 'no background survival test has been started'}
    test_id = latest.read_text(encoding='utf-8').strip()
    state_path = base / f'{test_id}.json'
    heartbeat_path = base / f'{test_id}.jsonl'
    if not state_path.is_file():
        return {'status': 'IN_PROGRESS', 'test_id': test_id, 'reason': 'worker has not written first state yet'}
    state = json.loads(state_path.read_text(encoding='utf-8'))
    beats: list[float] = []
    if heartbeat_path.is_file():
        for line in heartbeat_path.read_text(encoding='utf-8').splitlines():
            try:
                beats.append(float(json.loads(line)['at']))
            except Exception:
                continue
    return _background_test_evaluate(state, beats)


def _runtime(args):
    cfg = LocalSovereignConfig(Path(args.root).expanduser().resolve(), args.model, args.base_url)
    return AndroidSovereignRuntime(cfg)


def main():
    p = argparse.ArgumentParser(prog='hakim-android')
    p.add_argument('--root', default='~/hakim-workspace')
    p.add_argument('--model', default='')
    p.add_argument('--base-url', default='http://127.0.0.1:8080/v1')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init'); sub.add_parser('doctor'); sub.add_parser('approval-security-test')
    background = sub.add_parser('background-test')
    background.add_argument('action', choices=['start', 'status'])
    background.add_argument('--seconds', type=int, default=300)
    background.add_argument('--interval', type=int, default=5)
    enq = sub.add_parser('enqueue'); enq.add_argument('goal'); enq.add_argument('--priority', type=int, default=50)
    status = sub.add_parser('status'); status.add_argument('job_id', nargs='?')
    approval = sub.add_parser('approval-test'); approval.add_argument('--ttl', type=int, default=120)
    run = sub.add_parser('run-once'); run.add_argument('--max-steps', type=int, default=12)
    daemon = sub.add_parser('daemon'); daemon.add_argument('--interval', type=float, default=2.0); daemon.add_argument('--max-steps', type=int, default=12)
    args = p.parse_args(); rt = _runtime(args)
    if args.cmd == 'init':
        cid = rt.store.create_checkpoint({
            'goal': None,
            'status': 'android-initialized',
            'protected_invariants': [
                'human-sovereign-notification-gate',
                'local-browser-bootstrap-fallback-is-loopback-only-and-does-not-qualify-notifications',
            ],
        })
        rt.store.verify_checkpoint(cid); rt.store.promote_checkpoint(cid)
        print(json.dumps({'status':'PASS','root':str(rt.config.root),'checkpoint':cid}, ensure_ascii=False, indent=2)); return
    if args.cmd == 'doctor': print(json.dumps(rt.doctor(), ensure_ascii=False, indent=2)); return
    if args.cmd == 'approval-security-test':
        print(json.dumps(_approval_security_self_test(rt.broker), ensure_ascii=False, indent=2)); return
    if args.cmd == 'background-test':
        if args.action == 'start':
            result = _background_test_start(rt.config.root, args.seconds, args.interval)
        else:
            result = _background_test_status(rt.config.root)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return
    if args.cmd == 'enqueue': print(rt.store.enqueue_goal(args.goal, priority=args.priority)); return
    if args.cmd == 'status':
        print(json.dumps(rt.store.get_job(args.job_id) if args.job_id else {'queue':rt.store.queue_counts(),'lkg':rt.store.last_verified_checkpoint()}, ensure_ascii=False, indent=2)); return
    if args.cmd == 'approval-test':
        d = rt.broker.request_and_wait('approval-test', 'اختبار بوابة موافقة HAKIM Ω على هذا الهاتف.', risk='test', ttl_seconds=args.ttl)
        print(json.dumps(d.__dict__, ensure_ascii=False, indent=2)); return
    if rt.model is None:
        raise SystemExit('A local model is required. Start llama.cpp locally and pass --model.')
    loop = AndroidAgentLoop(rt.store, rt.workspace, rt.model, worker_id='omega-android-1')
    if args.cmd == 'run-once': print(loop.process_once(max_steps=args.max_steps)); return
    while True:
        result = loop.process_once(max_steps=args.max_steps)
        if result == 'idle': time.sleep(max(0.2, args.interval))


if __name__ == '__main__':
    main()
