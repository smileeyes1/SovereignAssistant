from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import (
    BoundedMissionRunner,
    CandidateScore,
    ImprovementSandbox,
    MissionStep,
    OutcomeAudit,
    OutcomeRecord,
)
from app.hakim.mission_kernel import MissionKernel, OperationalEnvelope


def _step(goal, env, *, capability="mission-step", ok=True, evidence=("accepted",), rollback=True, risk=ActionRisk.MODERATE):
    return MissionStep(goal, env, capability, risk, True, ("plan-evidence",), execute=lambda: (ok, tuple(evidence)), rollback=lambda: rollback)


def test_multi_environment_mission_records_durable_outcomes():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        run = BoundedMissionRunner(audit).run("m1", (_step("g1", "sandbox"), _step("g2", "canary"), _step("g3", "production")))
        assert run.completed and run.attempted == 3 and run.recovered == 0
        assert OutcomeAudit(DurableStateStore(db)).get("m1", "g3", "production")["status"] == "completed"


def test_completed_step_replay_reuses_durable_outcome_without_reexecution():
    touched = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        step = MissionStep("g1", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("executed") or True, ("first-run",)), rollback=lambda: True)
        first = BoundedMissionRunner(audit).run("replay-safe", (step,))
        second = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("replay-safe", (step,))
    assert first.completed and second.completed
    assert touched == ["executed"]
    assert second.outcomes[0].evidence == ("first-run",)


def test_ambiguous_reserved_step_fails_closed_without_duplicate_execution():
    touched = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        assert audit.reserve_execution("crash-gap", "g1", "production")
        step = MissionStep("g1", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("duplicate") or True, ("bad",)), rollback=lambda: True)
        run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("crash-gap", (step,))
    assert not run.completed and run.outcomes[0].status == "blocked"
    assert "reservation already exists" in run.outcomes[0].evidence[0]
    assert touched == []


def test_proven_rollback_releases_only_compensated_slot_for_retry():
    touched = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        first = MissionStep("g1", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("first") or False, ()), rollback=lambda: True)
        first_run = BoundedMissionRunner(audit).run("retry-safe", (first,))
        assert not first_run.completed and first_run.outcomes[0].status == "rolled_back"
        retry = MissionStep("g1", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("retry") or True, ("retry-completed",)), rollback=lambda: True)
        second_run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("retry-safe", (retry,))
        third_run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("retry-safe", (retry,))
    assert second_run.completed and third_run.completed
    assert touched == ["first", "retry"]
    assert second_run.outcomes[0].evidence == ("retry-completed",)


def test_restart_reconciles_crash_after_rollback_record_before_compensation():
    touched = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        assert audit.reserve_execution("rollback-gap", "g1", "production")
        audit.record(OutcomeRecord("rollback-gap", "g1", "production", "rolled_back", (), True))
        retry = MissionStep("g1", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("retry") or True, ("recovered",)), rollback=lambda: True)
        run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("rollback-gap", (retry,))
    assert run.completed and touched == ["retry"] and run.outcomes[0].evidence == ("recovered",)


def test_failed_step_rolls_back_and_stops_later_environment():
    touched = []
    first = _step("g1", "sandbox", ok=False, evidence=())
    second = MissionStep("g2", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("production") or True, ("should-not-run",)), rollback=lambda: True)
    with TemporaryDirectory() as tmp:
        run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp) / "omega.db"))).run("m2", (first, second))
    assert not run.completed and run.attempted == 1 and run.recovered == 1
    assert run.outcomes[0].status == "rolled_back" and touched == []


def test_kernel_denial_blocks_execution():
    touched = []
    denied = MissionStep("unsafe", "production", "outside-envelope", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("executed") or True, ("bad",)), rollback=lambda: True)
    kernel = MissionKernel(OperationalEnvelope(frozenset({"mission-step"}), max_risk=2, min_evidence=1))
    with TemporaryDirectory() as tmp:
        run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp) / "omega.db")), mission_kernel=kernel).run("m3", (denied,))
    assert not run.completed and run.outcomes[0].status == "blocked" and touched == []


def test_consequential_step_requires_verified_human_approval_and_audits_proof():
    touched = []
    observed = []
    step = MissionStep("consequential", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",), execute=lambda: (touched.append("executed") or True, ("result-proof",)), rollback=lambda: True, requires_human_approval=True)
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        no_verifier = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run("approval-none", (step,))
        rejected = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db)), approval_verifier=lambda mission_id, _: (False, (f"rejected:{mission_id}",))).run("approval-rejected", (step,))
        empty_proof = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db)), approval_verifier=lambda mission_id, _: (True, ())).run("approval-empty", (step,))
        def verify(mission_id, verified_step):
            observed.append((mission_id, verified_step.goal_id, verified_step.environment))
            return True, (f"human-approval:{mission_id}:request-123",)
        approved = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db)), approval_verifier=verify).run("approval-proven", (step,))
    assert not no_verifier.completed and no_verifier.outcomes[0].status == "blocked"
    assert not rejected.completed and rejected.outcomes[0].status == "blocked"
    assert not empty_proof.completed and empty_proof.outcomes[0].status == "blocked"
    assert approved.completed and touched == ["executed"]
    assert observed == [("approval-proven", "consequential", "production")]
    assert approved.outcomes[0].evidence == ("result-proof", "human-approval:approval-proven:request-123")


def test_improvement_sandbox_canary_failure_rolls_back_to_champion():
    sandbox = ImprovementSandbox()
    decision = sandbox.choose(CandidateScore("champion", 0.8, 1.0, True), CandidateScore("challenger", 0.9, 1.0, True))
    assert decision.promote
    rollback = sandbox.canary(decision, lambda: False)
    assert not rollback.promote and rollback.selected == "champion"
