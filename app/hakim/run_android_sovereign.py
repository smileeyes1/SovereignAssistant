"""Android/Termux runner for HAKIM Ω with local human approval gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

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
