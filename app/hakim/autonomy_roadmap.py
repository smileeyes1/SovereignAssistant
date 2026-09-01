"""Default completion roadmap for Ω APEX self-development.

The roadmap is seeded once into durable state. It is deliberately finite and
acceptance-oriented: the goal governor may evolve implementation, but completion
must still flow through CI/merge evidence.
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
        context_paths=(
            "app/hakim/autonomy_service.py",
            "tests/test_autonomy_service.py",
        ),
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
        context_paths=(
            "app/hakim/core.py",
            "app/hakim/durable_state.py",
            "app/hakim/goal_governor.py",
        ),
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
        context_paths=(
            "app/hakim/coding_provider.py",
            "app/hakim/durable_state.py",
            "app/hakim/recovery_governor.py",
        ),
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
        context_paths=(
            "app/hakim/durable_worker.py",
            "app/hakim/ingress_supervisor.py",
            "app/hakim/goal_governor.py",
        ),
    ),
)
