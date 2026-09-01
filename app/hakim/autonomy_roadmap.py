"""Default completion roadmap for Ω APEX self-development.

The roadmap is acceptance-oriented and intentionally extends through mission
liveness and evidence-backed autonomy. A runtime may evolve implementation, but
no level is complete without explicit acceptance evidence and release gates.
"""
from __future__ import annotations

from .goal_governor import Goal


DEFAULT_AUTONOMY_ROADMAP: tuple[Goal, ...] = (
    Goal(
        "ingress-hardening",
        "Harden autonomous ingress boundaries",
        "Harden webhook/runtime ingress against oversized requests and malformed/untrusted inputs while preserving authenticated event delivery.",
        100,
        acceptance=(
            "request body size is bounded before full processing",
            "invalid or oversized requests fail closed",
            "existing authenticated GitHub and runtime webhook tests remain green",
        ),
        context_paths=("app/hakim/autonomy_service.py", "tests/test_autonomy_service.py"),
    ),
    Goal(
        "completion-auditor",
        "Add independent completion auditor",
        "Add an independent, evidence-based completion gate that refuses to mark outcomes complete when acceptance evidence or required checks are missing.",
        90,
        dependencies=("ingress-hardening",),
        acceptance=(
            "completion is fail-closed when required evidence is absent",
            "completion evidence is persisted durably",
            "auditor behavior has adversarial regression tests",
        ),
        context_paths=("app/hakim/core.py", "app/hakim/durable_state.py", "app/hakim/goal_governor.py"),
    ),
    Goal(
        "capability-registry",
        "Persist capability and provider health registry",
        "Add a durable registry that records available providers/tools, health, failures and selection evidence so failover decisions survive restart.",
        80,
        dependencies=("completion-auditor",),
        acceptance=(
            "provider/tool health survives process restart",
            "unhealthy capabilities are excluded from selection",
            "recovery after a healthy signal is tested",
        ),
        context_paths=("app/hakim/coding_provider.py", "app/hakim/durable_state.py", "app/hakim/recovery_governor.py"),
    ),
    Goal(
        "autonomy-self-audit",
        "Add autonomous system self-audit",
        "Continuously evaluate the autonomous runtime for stalled goals, dead-letter work, exhausted repair budgets and missing capabilities, and emit actionable continuation events instead of silently stopping.",
        70,
        dependencies=("capability-registry",),
        acceptance=(
            "stalled/dead states are detected deterministically",
            "safe recovery events are emitted durably",
            "irrecoverable states are recorded with explicit blocker evidence",
        ),
        context_paths=("app/hakim/durable_worker.py", "app/hakim/ingress_supervisor.py", "app/hakim/goal_governor.py"),
    ),
    Goal(
        "mission-liveness",
        "Enforce proactive mission liveness",
        "Make unfinished mission state itself a continuation condition: heartbeat-generated next work must execute in the same drain cycle, while hard budgets detect stalls and prevent runaway loops.",
        65,
        dependencies=("autonomy-self-audit",),
        acceptance=(
            "idle is provisional while a safe ready goal exists",
            "heartbeat-generated continuation executes in the same supervisor drain",
            "bounded work budgets prevent infinite self-trigger loops",
            "missing execution capabilities become explicit blockers rather than silent idle",
        ),
        context_paths=("app/hakim/ingress_supervisor.py", "app/hakim/self_audit.py", "tests/test_ingress_supervisor.py"),
    ),
    Goal(
        "omega-l5-survival",
        "Certify ΩL5 survival and degraded operation",
        "Add FDIR, degraded modes, watchdog evidence, crash/restart/replay tests and diverse provider/tool failover; raise Autonomy Arena only when those behaviors pass as release gates.",
        60,
        dependencies=("mission-liveness",),
        acceptance=(
            "fault detection isolation diagnosis and recovery are explicit and durable",
            "degraded mode preserves safe useful operation when a primary capability is lost",
            "crash restart and replay recover without duplicate consequential execution",
            "Autonomy Arena certifies ΩL5 from independent fault scenarios",
        ),
        context_paths=("app/hakim/autonomy_arena.py", "app/hakim/run_arena_gate.py", "app/hakim/recovery_governor.py", "app/hakim/durable_worker.py"),
    ),
    Goal(
        "omega-l6-reconstruction",
        "Certify ΩL6 state reconstruction and diverse assurance",
        "Reconstruct canonical mission state from durable evidence after component loss, add independent verifier diversity and digital-twin/fault-injection coverage, then gate ΩL6 on evidence.",
        50,
        dependencies=("omega-l5-survival",),
        acceptance=(
            "canonical state can be reconstructed from Git events database checkpoints tests and evidence",
            "independent verification disagrees fail-closed on consequential claims",
            "digital twin and injected faults exercise component-loss recovery",
            "Autonomy Arena certifies ΩL6 only from reconstruction and diverse-verification evidence",
        ),
        context_paths=("app/hakim/durable_state.py", "app/hakim/completion_auditor.py", "app/hakim/autonomy_arena.py"),
    ),
    Goal(
        "omega-l7-mission-autonomy",
        "Certify ΩL7 bounded mission autonomy",
        "Demonstrate closed-loop mission autonomy within the supported operational envelope: select goal, plan, execute, verify, recover, persist outcome, select next goal and continue without daily human management while preserving authority gates.",
        40,
        dependencies=("omega-l6-reconstruction",),
        acceptance=(
            "multi-goal mission portfolio advances end-to-end without silent idle between executable goals",
            "consequential authority boundaries remain fail-closed",
            "long-duration soak includes injected failures recovery rollback and outcome audit",
            "final acceptance audit certifies ΩL7 only inside the declared operational envelope",
        ),
        context_paths=("app/hakim/goal_governor.py", "app/hakim/goal_loop.py", "app/hakim/mission_kernel.py", "app/hakim/autonomy_arena.py"),
    ),
)
