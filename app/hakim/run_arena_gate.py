"""Executable Ω APEX autonomy certification gate used by CI releases."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .autonomy_arena import AutonomyArena, OmegaLevel, baseline_scenarios
from .capability_registry import CapabilityRegistry
from .durable_state import DurableStateStore
from .durable_worker import DurableWorkQueue
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope


def restart_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        first = DurableWorkQueue(db)
        assert first.enqueue("arena-restart", "task_completed", "restart", {"probe": True})
        second = DurableWorkQueue(db)
        item = second.get("arena-restart")
        return item is not None and item.status == "pending" and item.payload == {"probe": True}


def duplicate_event_probe() -> bool:
    with TemporaryDirectory() as tmp:
        queue = DurableWorkQueue(Path(tmp) / "omega.db")
        first = queue.enqueue("arena-duplicate", "task_completed", "dup", {})
        second = queue.enqueue("arena-duplicate", "task_completed", "dup", {})
        return first is True and second is False


def provider_failover_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        registry = CapabilityRegistry(DurableStateStore(db), failure_threshold=2)
        registry.record_failure("primary", "timeout")
        registry.record_failure("primary", "timeout")
        if registry.is_healthy("primary"):
            return False
        # Reconstruct from durable state, then prove recovery is explicit.
        restarted = CapabilityRegistry(DurableStateStore(db), failure_threshold=2)
        if restarted.is_healthy("primary"):
            return False
        restarted.record_success("primary")
        return restarted.is_healthy("primary")


def unsafe_action_probe() -> bool:
    kernel = MissionKernel(
        OperationalEnvelope(frozenset({"patch", "rollback"}), max_risk=2, require_reversible_above=1, min_evidence=1)
    )
    unsafe = MissionAction(
        "irreversible-prod-mutation",
        "patch",
        2,
        False,
        AuthorityLevel.CONSEQUENTIAL,
        ("arena",),
    )
    return kernel.evaluate(unsafe, human_approved=False).allowed is False


def main() -> None:
    scenarios = baseline_scenarios(
        restart_probe=restart_probe,
        duplicate_event_probe=duplicate_event_probe,
        provider_failover_probe=provider_failover_probe,
        unsafe_action_probe=unsafe_action_probe,
    )
    arena = AutonomyArena()
    report = arena.run(scenarios)
    certification = arena.certify(OmegaLevel.L3, scenarios, report)
    output = {
        "requested_level": certification.level.name,
        "certified": certification.certified,
        "evidence_count": certification.evidence_count,
        "pass_rate": report.pass_rate,
        "reasons": list(certification.reasons),
        "scenarios": [
            {"id": item.scenario_id, "passed": item.passed, "category": item.category, "severity": item.severity, "error": item.error}
            for item in report.results
        ],
    }
    Path(".omega").mkdir(exist_ok=True)
    Path(".omega/autonomy-certification.json").write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    if not certification.certified:
        raise SystemExit("Ω autonomy certification gate failed")


if __name__ == "__main__":
    main()
