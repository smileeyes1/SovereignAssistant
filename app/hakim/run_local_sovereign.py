"""Command-line entry point for HAKIM Ω local sovereign mode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .local_sovereign import LocalAgentLoop, LocalSovereignConfig, LocalSovereignRuntime


def _runtime(args) -> LocalSovereignRuntime:
    return LocalSovereignRuntime(LocalSovereignConfig(Path(args.root).expanduser().resolve(), args.model, args.base_url))


def main() -> None:
    parser = argparse.ArgumentParser(prog="hakim-local")
    parser.add_argument("--root", default="~/hakim-workspace")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    enq = sub.add_parser("enqueue"); enq.add_argument("goal"); enq.add_argument("--priority", type=int, default=50)
    status = sub.add_parser("status"); status.add_argument("job_id", nargs="?")
    backup = sub.add_parser("backup"); backup.add_argument("--label", default="manual")
    run = sub.add_parser("run-once"); run.add_argument("--max-steps", type=int, default=12)
    daemon = sub.add_parser("daemon"); daemon.add_argument("--interval", type=float, default=2.0); daemon.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    rt = _runtime(args)

    if args.cmd == "init":
        cid = rt.store.create_checkpoint({"goal": None, "status": "initialized", "protected_invariants": []})
        rt.store.verify_checkpoint(cid); rt.store.promote_checkpoint(cid)
        print(json.dumps({"status":"PASS","root":str(rt.config.root),"checkpoint":cid}, ensure_ascii=False, indent=2)); return
    if args.cmd == "doctor": print(json.dumps(rt.doctor(), ensure_ascii=False, indent=2)); return
    if args.cmd == "enqueue": print(rt.store.enqueue_goal(args.goal, priority=args.priority)); return
    if args.cmd == "status":
        print(json.dumps(rt.store.get_job(args.job_id) if args.job_id else {"queue": rt.store.queue_counts(), "lkg": rt.store.last_verified_checkpoint()}, ensure_ascii=False, indent=2)); return
    if args.cmd == "backup":
        p = rt.backups.create(label=args.label); print(json.dumps({"status":"PASS","backup":str(p)}, ensure_ascii=False, indent=2)); return
    if rt.model is None:
        raise SystemExit("A local model is required for run-once/daemon. Pass --model and start a local OpenAI-compatible server such as llama.cpp.")
    loop = LocalAgentLoop(rt.store, rt.workspace, rt.model)
    if args.cmd == "run-once": print(loop.process_once(max_steps=args.max_steps)); return
    if args.cmd == "daemon":
        while True:
            result = loop.process_once(max_steps=args.max_steps)
            if result == "idle": time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    main()
