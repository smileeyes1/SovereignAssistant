"""Executable Ω APEX autonomy certification gate used by CI releases."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .autonomy_arena import ArenaScenario, AutonomyArena, OmegaLevel, baseline_scenarios
from .capability_registry import CapabilityRegistry
from .coding_provider import CodingProviderPool, PatchPlan, PatchRequest
from .core import ActionRisk
from .durable_state import DurableStateStore
from .durable_worker import DurableWorkQueue
from .event_continuation import ContinuationEvent, EventType
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope
from .recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim
from .survival_controller import FailureClass, OperatingMode, SurvivalController


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


def runtime_kernel_enforcement_probe() -> bool:
    with TemporaryDirectory() as tmp:
        state = DurableStateStore(Path(tmp) / "omega.db")
        registry = ActionRegistry()
        registry.register(
            RegisteredAction(
                name="critical-runtime-action",
                event_types=(EventType.MANUAL_SIGNAL,),
                value=100,
                risk=ActionRisk.CRITICAL,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("critical action observed", "arena"),
                executor=lambda event: (_ for _ in ()).throw(AssertionError("blocked action executed")),
            )
        )
        governor = RecoveryGovernor(registry, state)
        event = ContinuationEvent("arena-runtime-kernel", EventType.MANUAL_SIGNAL, "runtime", {})
        candidate = governor.candidates(event)[0]
        denial = state.get_state("omega.mission_kernel.last_denial.critical-runtime-action")
        return candidate.safe is False and isinstance(denial, dict) and denial.get("reason") == "risk exceeds operational envelope"


def crash_restart_replay_probe() -> bool:
    """A leased event survives worker loss and is replayed once after lease expiry."""
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        queue = DurableWorkQueue(db)
        assert queue.enqueue("arena-crash-replay", "task_completed", "crash", {"n": 1})
        claimed = queue.claim("dead-worker", lease_seconds=60)
        if claimed is None or claimed.status != "leased" or claimed.attempts != 1:
            return False
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with queue._connect() as conn:
            conn.execute("UPDATE work_queue SET lease_until=? WHERE job_id=?", (past, claimed.job_id))
        restarted = DurableWorkQueue(db)
        replay = restarted.claim("replacement-worker", lease_seconds=60)
        if replay is None or replay.job_id != claimed.job_id or replay.attempts != 2:
            return False
        if not restarted.complete(replay.job_id, "replacement-worker"):
            return False
        return restarted.enqueue("arena-crash-replay", "task_completed", "crash", {"n": 1}) is False


def degraded_mode_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        controller = SurvivalController(DurableStateStore(db))
        decision = controller.diagnose("primary-tool", FailureClass.CAPABILITY_LOSS, fallback="safe-secondary-tool")
        if decision.mode != OperatingMode.DEGRADED or not decision.isolated:
            return False
        restarted = SurvivalController(DurableStateStore(db))
        persisted = restarted.status("primary-tool")
        return persisted.get("mode") == "degraded" and persisted.get("fallback") == "safe-secondary-tool"


def fdir_fail_closed_probe() -> bool:
    with TemporaryDirectory() as tmp:
        controller = SurvivalController(DurableStateStore(Path(tmp) / "omega.db"))
        safety = controller.diagnose("unsafe-tool", FailureClass.SAFETY_VIOLATION, fallback="alternate")
        state = controller.diagnose("mission-state", FailureClass.STATE_CORRUPTION, fallback="cache")
        return (
            safety.mode == OperatingMode.BLOCKED
            and safety.recovery == "fail-closed"
            and safety.fallback is None
            and state.mode == OperatingMode.BLOCKED
            and state.recovery == "fail-closed"
        )


def diverse_provider_failover_probe() -> bool:
    class FailingProvider:
        name = "provider-a"

        def propose_patch(self, request: PatchRequest) -> PatchPlan:
            raise RuntimeError("injected provider outage")

    class HealthyProvider:
        name = "provider-b"

        def propose_patch(self, request: PatchRequest) -> PatchPlan:
            return PatchPlan(self.name, "safe fallback", {"README.md": "fallback"})

    with TemporaryDirectory() as tmp:
        capabilities = CapabilityRegistry(DurableStateStore(Path(tmp) / "omega.db"), failure_threshold=1)
        pool = CodingProviderPool([FailingProvider(), HealthyProvider()], capabilities)
        plan = pool.propose_patch(PatchRequest("arena failover", "", {}))
        return (
            plan.provider == "provider-b"
            and not capabilities.is_healthy("provider-a")
            and capabilities.is_healthy("provider-b")
            and any(name == "provider-a" for name, _ in pool.failures)
        )


def main() -> None:
    scenarios = baseline_scenarios(
        restart_probe=restart_probe,
        duplicate_event_probe=duplicate_event_probe,
        provider_failover_probe=provider_failover_probe,
        unsafe_action_probe=unsafe_action_probe,
    ) + (
        ArenaScenario(
            "runtime-mission-kernel-enforcement",
            "mission-control",
            5,
            OmegaLevel.L4,
            runtime_kernel_enforcement_probe,
        ),
        ArenaScenario("crash-restart-replay", "runtime-survival", 5, OmegaLevel.L5, crash_restart_replay_probe),
        ArenaScenario("degraded-mode-persistence", "degraded-operation", 4, OmegaLevel.L5, degraded_mode_probe),
        ArenaScenario("fdir-fail-closed", "fault-isolation", 5, OmegaLevel.L5, fdir_fail_closed_probe),
        ArenaScenario("diverse-provider-failover", "provider-diversity", 4, OmegaLevel.L5, diverse_provider_failover_probe),
    )
    arena = AutonomyArena()
    report = arena.run(scenarios)
    certification = arena.certify(OmegaLevel.L5, scenarios, report)
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
