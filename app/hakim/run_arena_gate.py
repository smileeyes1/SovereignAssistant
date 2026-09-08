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
from .mission_autonomy import BoundedMissionRunner, CandidateScore, ImprovementSandbox, MissionStep, OutcomeAudit
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope
from .recovery_governor import ActionRegistry, RecoveryGovernor, RegisteredAction, strong_claim
from .state_reconstruction import CanonicalStateReconstructor, DiverseVerifier, DurableStateEvidence, EvidenceView, VerificationOpinion, VerificationVerdict, checkpoint_view
from .survival_controller import FailureClass, OperatingMode, SurvivalController


def restart_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"; first = DurableWorkQueue(db)
        assert first.enqueue("arena-restart", "task_completed", "restart", {"probe": True})
        item = DurableWorkQueue(db).get("arena-restart")
        return item is not None and item.status == "pending" and item.payload == {"probe": True}


def duplicate_event_probe() -> bool:
    with TemporaryDirectory() as tmp:
        queue = DurableWorkQueue(Path(tmp) / "omega.db")
        return queue.enqueue("arena-duplicate", "task_completed", "dup", {}) is True and queue.enqueue("arena-duplicate", "task_completed", "dup", {}) is False


def provider_failover_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"; registry = CapabilityRegistry(DurableStateStore(db), failure_threshold=2)
        registry.record_failure("primary", "timeout"); registry.record_failure("primary", "timeout")
        if registry.is_healthy("primary") or CapabilityRegistry(DurableStateStore(db), failure_threshold=2).is_healthy("primary"): return False
        restarted = CapabilityRegistry(DurableStateStore(db), failure_threshold=2); restarted.record_success("primary")
        return restarted.is_healthy("primary")


def unsafe_action_probe() -> bool:
    kernel = MissionKernel(OperationalEnvelope(frozenset({"patch", "rollback"}), max_risk=2, require_reversible_above=1, min_evidence=1))
    return not kernel.evaluate(MissionAction("irreversible-prod-mutation", "patch", 2, False, AuthorityLevel.CONSEQUENTIAL, ("arena",)), human_approved=False).allowed


def runtime_kernel_enforcement_probe() -> bool:
    with TemporaryDirectory() as tmp:
        state = DurableStateStore(Path(tmp) / "omega.db"); registry = ActionRegistry()
        registry.register(RegisteredAction(name="critical-runtime-action", event_types=(EventType.MANUAL_SIGNAL,), value=100, risk=ActionRisk.CRITICAL, reversible=True, requires_human_approval=False, claim_factory=lambda event: strong_claim("critical action observed", "arena"), executor=lambda event: (_ for _ in ()).throw(AssertionError("blocked action executed"))))
        event = ContinuationEvent("arena-runtime-kernel", EventType.MANUAL_SIGNAL, "runtime", {}); candidate = RecoveryGovernor(registry, state).candidates(event)[0]
        denial = state.get_state("omega.mission_kernel.last_denial.critical-runtime-action")
        return candidate.safe is False and isinstance(denial, dict) and denial.get("reason") == "risk exceeds operational envelope"


def crash_restart_replay_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"; queue = DurableWorkQueue(db); assert queue.enqueue("arena-crash-replay", "task_completed", "crash", {"n": 1})
        claimed = queue.claim("dead-worker", lease_seconds=60)
        if claimed is None or claimed.status != "leased" or claimed.attempts != 1: return False
        with queue._connect() as conn: conn.execute("UPDATE work_queue SET lease_until=? WHERE job_id=?", ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), claimed.job_id))
        restarted = DurableWorkQueue(db); replay = restarted.claim("replacement-worker", lease_seconds=60)
        return replay is not None and replay.job_id == claimed.job_id and replay.attempts == 2 and restarted.complete(replay.job_id, "replacement-worker") and restarted.enqueue("arena-crash-replay", "task_completed", "crash", {"n": 1}) is False


def degraded_mode_probe() -> bool:
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"; controller = SurvivalController(DurableStateStore(db)); decision = controller.diagnose("primary-tool", FailureClass.CAPABILITY_LOSS, fallback="safe-secondary-tool")
        persisted = SurvivalController(DurableStateStore(db)).status("primary-tool")
        return decision.mode == OperatingMode.DEGRADED and decision.isolated and persisted.get("mode") == "degraded" and persisted.get("fallback") == "safe-secondary-tool"


def fdir_fail_closed_probe() -> bool:
    with TemporaryDirectory() as tmp:
        controller = SurvivalController(DurableStateStore(Path(tmp) / "omega.db")); safety = controller.diagnose("unsafe-tool", FailureClass.SAFETY_VIOLATION, fallback="alternate"); state = controller.diagnose("mission-state", FailureClass.STATE_CORRUPTION, fallback="cache")
        return safety.mode == OperatingMode.BLOCKED and safety.recovery == "fail-closed" and safety.fallback is None and state.mode == OperatingMode.BLOCKED and state.recovery == "fail-closed"


def diverse_provider_failover_probe() -> bool:
    class FailingProvider:
        name="provider-a"
        def propose_patch(self, request): raise RuntimeError("injected provider outage")
    class HealthyProvider:
        name="provider-b"
        def propose_patch(self, request): return PatchPlan(self.name, "safe fallback", {"README.md":"fallback"})
    with TemporaryDirectory() as tmp:
        capabilities=CapabilityRegistry(DurableStateStore(Path(tmp)/"omega.db"), failure_threshold=1); pool=CodingProviderPool([FailingProvider(),HealthyProvider()],capabilities); plan=pool.propose_patch(PatchRequest("arena failover","",{}))
        return plan.provider=="provider-b" and not capabilities.is_healthy("provider-a") and capabilities.is_healthy("provider-b") and any(name=="provider-a" for name,_ in pool.failures)


def canonical_reconstruction_probe() -> bool:
    with TemporaryDirectory() as tmp:
        root=Path(tmp); db=root/"omega.db"; store=DurableStateStore(db); store.set_state("mission.phase","verifying"); checkpoint=root/"checkpoint.json"; checkpoint.write_text(json.dumps("verifying"),encoding="utf-8")
        views=(DurableStateEvidence(DurableStateStore(db)).state_view("mission.phase",strength=1.0),checkpoint_view(checkpoint,"mission.phase",strength=0.9),EvidenceView("git-main","mission.phase","verifying",0.95),EvidenceView("test-result","mission.phase","verifying",0.95)); canonical=CanonicalStateReconstructor().reconstruct("mission.phase",views)
        return canonical.value=="verifying" and not canonical.conflict and len(canonical.sources)==4


def reconstruction_conflict_probe() -> bool:
    canonical=CanonicalStateReconstructor().reconstruct("mission.outcome",(EvidenceView("durable-db","mission.outcome","complete",1.0),EvidenceView("git-evidence","mission.outcome","verifying",1.0)))
    return canonical.conflict and canonical.value is None


def diverse_verifier_fail_closed_probe() -> bool:
    verifier=DiverseVerifier(); accepted=verifier.decide((VerificationOpinion("deterministic-checker",VerificationVerdict.ACCEPT,"deterministic-digest"),VerificationOpinion("runtime-replay",VerificationVerdict.ACCEPT,"runtime-digest"))); disagreement=verifier.decide((VerificationOpinion("deterministic-checker",VerificationVerdict.ACCEPT,"deterministic-digest"),VerificationOpinion("runtime-replay",VerificationVerdict.REJECT,"runtime-digest"))); common=verifier.decide((VerificationOpinion("checker-a",VerificationVerdict.ACCEPT,"same-evidence"),VerificationOpinion("checker-b",VerificationVerdict.ACCEPT,"same-evidence")))
    return accepted.allowed and not disagreement.allowed and not common.allowed


def component_loss_digital_twin_probe() -> bool:
    r=CanonicalStateReconstructor(); recovered=r.reconstruct("goal:g1",(EvidenceView("durable-db","goal:g1",{"status":"verifying"},1.0),EvidenceView("git-pr","goal:g1",{"status":"verifying"},1.0),EvidenceView("lost-cache","goal:g1",{"status":"completed"},0.2))); conflict=r.reconstruct("goal:g2",(EvidenceView("durable-db","goal:g2",{"status":"completed"},1.0),EvidenceView("git-pr","goal:g2",{"status":"verifying"},1.0)))
    return recovered.value=={"status":"verifying"} and not recovered.conflict and conflict.conflict


def governed_multi_environment_probe() -> bool:
    with TemporaryDirectory() as tmp:
        audit=OutcomeAudit(DurableStateStore(Path(tmp)/"omega.db")); executed=[]; steps=tuple(MissionStep(f"goal-{i}",env,"mission-step",ActionRisk.MODERATE,True,(f"plan-{env}",),execute=lambda env=env:(executed.append(env) or True,(f"evidence-{env}",)),rollback=lambda:True) for i,env in enumerate(("sandbox","canary","production"),1)); run=BoundedMissionRunner(audit).run("arena-mission",steps); restarted=OutcomeAudit(DurableStateStore(Path(tmp)/"omega.db"))
        return run.completed and executed==["sandbox","canary","production"] and restarted.get("arena-mission","goal-3","production").get("status")=="completed"


def mission_kernel_bypass_denied_probe() -> bool:
    touched=[]; denied=MissionStep("unsafe-goal","production","outside-envelope",ActionRisk.MODERATE,True,("plan-evidence",),execute=lambda:(touched.append("executed") or True,("bad",)),rollback=lambda:True)
    with TemporaryDirectory() as tmp: run=BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp)/"omega.db"))).run("arena-denial",(denied,))
    return not run.completed and run.outcomes[0].status=="blocked" and touched==[]


def rollback_stops_environment_escalation_probe() -> bool:
    touched=[]; first=MissionStep("canary-failure","canary","mission-step",ActionRisk.MODERATE,True,("plan-canary",),execute=lambda:(False,()),rollback=lambda:True); second=MissionStep("production-after-failure","production","mission-step",ActionRisk.MODERATE,True,("plan-production",),execute=lambda:(touched.append("production") or True,("unexpected",)),rollback=lambda:True)
    with TemporaryDirectory() as tmp: run=BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp)/"omega.db"))).run("arena-rollback",(first,second))
    return not run.completed and run.recovered==1 and run.attempted==1 and touched==[]


def champion_challenger_canary_probe() -> bool:
    sandbox=ImprovementSandbox(); chosen=sandbox.choose(CandidateScore("champion",.80,1.0,True),CandidateScore("challenger",.90,1.0,True)); rollback=sandbox.canary(chosen,lambda:False); safe=sandbox.choose(CandidateScore("champion",.80,1.0,True),CandidateScore("unsafe-challenger",.99,.5,True))
    return chosen.promote and not rollback.promote and rollback.selected=="champion" and not safe.promote


def bounded_soak_continuity_probe() -> bool:
    """Deterministic soak with injected execution failures, rollback, restart and outcome audit."""
    with TemporaryDirectory() as tmp:
        db=Path(tmp)/"omega.db"; failures=rollbacks=recoveries=0
        for cycle in range(100):
            should_fail=cycle in {17,53,89}; attempts=[]
            def execute(c=cycle, fail=should_fail):
                attempts.append(c)
                return (not fail,(f"outcome-{c}",) if not fail else ())
            audit=OutcomeAudit(DurableStateStore(db)); step=MissionStep("goal","sandbox" if cycle%2==0 else "canary","mission-step",ActionRisk.MODERATE,True,(f"plan-{cycle}",),execute=execute,rollback=lambda:True); run=BoundedMissionRunner(audit).run(f"soak-{cycle}",(step,))
            if should_fail:
                failures+=1
                if run.completed or run.recovered!=1 or run.outcomes[0].status!="rolled_back": return False
                rollbacks+=1
                retry=MissionStep("goal",step.environment,"mission-step",ActionRisk.MODERATE,True,(f"retry-plan-{cycle}",),execute=lambda c=cycle:(True,(f"recovered-{c}",)),rollback=lambda:True)
                restarted=BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run(f"soak-{cycle}",(retry,))
                if not restarted.completed or restarted.outcomes[0].evidence!=(f"recovered-{cycle}",): return False
                recoveries+=1
            elif not run.completed: return False
        audit=OutcomeAudit(DurableStateStore(db)); final=audit.get("soak-99","goal","canary")
        recovered=audit.get("soak-89","goal","canary")
        return failures==3 and rollbacks==3 and recoveries==3 and final.get("status")=="completed" and final.get("evidence")==["outcome-99"] and recovered.get("status")=="completed" and recovered.get("evidence")==["recovered-89"]


def main() -> None:
    scenarios=baseline_scenarios(restart_probe=restart_probe,duplicate_event_probe=duplicate_event_probe,provider_failover_probe=provider_failover_probe,unsafe_action_probe=unsafe_action_probe)+(
        ArenaScenario("runtime-mission-kernel-enforcement","mission-control",5,OmegaLevel.L4,runtime_kernel_enforcement_probe),ArenaScenario("crash-restart-replay","runtime-survival",5,OmegaLevel.L5,crash_restart_replay_probe),ArenaScenario("degraded-mode-persistence","degraded-operation",4,OmegaLevel.L5,degraded_mode_probe),ArenaScenario("fdir-fail-closed","fault-isolation",5,OmegaLevel.L5,fdir_fail_closed_probe),ArenaScenario("diverse-provider-failover","provider-diversity",4,OmegaLevel.L5,diverse_provider_failover_probe),ArenaScenario("canonical-state-reconstruction","state-reconstruction",5,OmegaLevel.L6,canonical_reconstruction_probe),ArenaScenario("reconstruction-conflict-fail-closed","state-conflict",5,OmegaLevel.L6,reconstruction_conflict_probe),ArenaScenario("diverse-verifier-fail-closed","independent-assurance",5,OmegaLevel.L6,diverse_verifier_fail_closed_probe),ArenaScenario("component-loss-digital-twin","fault-injection",5,OmegaLevel.L6,component_loss_digital_twin_probe),ArenaScenario("governed-multi-environment-mission","mission-autonomy",5,OmegaLevel.L7,governed_multi_environment_probe),ArenaScenario("mission-kernel-bypass-denied","mission-safety",5,OmegaLevel.L7,mission_kernel_bypass_denied_probe),ArenaScenario("rollback-stops-environment-escalation","mission-recovery",5,OmegaLevel.L7,rollback_stops_environment_escalation_probe),ArenaScenario("champion-challenger-canary","self-improvement",4,OmegaLevel.L7,champion_challenger_canary_probe),ArenaScenario("bounded-soak-continuity","long-duration",4,OmegaLevel.L7,bounded_soak_continuity_probe),)
    arena=AutonomyArena(); report=arena.run(scenarios); certification=arena.certify(OmegaLevel.L7,scenarios,report); output={"requested_level":certification.level.name,"certified":certification.certified,"evidence_count":certification.evidence_count,"pass_rate":report.pass_rate,"reasons":list(certification.reasons),"scenarios":[{"id":i.scenario_id,"passed":i.passed,"category":i.category,"severity":i.severity,"error":i.error} for i in report.results]}; Path(".omega").mkdir(exist_ok=True); Path(".omega/autonomy-certification.json").write_text(json.dumps(output,indent=2,sort_keys=True),encoding="utf-8"); print(json.dumps(output,sort_keys=True))
    if not certification.certified: raise SystemExit("Ω autonomy certification gate failed")


if __name__=="__main__": main()
