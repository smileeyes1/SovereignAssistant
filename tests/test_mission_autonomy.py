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
)
from app.hakim.mission_kernel import MissionKernel, OperationalEnvelope


def _step(goal, env, *, capability="mission-step", ok=True, evidence=("accepted",), rollback=True, risk=ActionRisk.MODERATE):
    return MissionStep(
        goal,
        env,
        capability,
        risk,
        True,
        ("plan-evidence",),
        execute=lambda: (ok, tuple(evidence)),
        rollback=lambda: rollback,
    )


def test_multi_environment_mission_records_durable_outcomes():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        run = BoundedMissionRunner(audit).run(
            "m1",
            (_step("g1", "sandbox"), _step("g2", "canary"), _step("g3", "production")),
        )
        assert run.completed and run.attempted == 3 and run.recovered == 0
        restarted = OutcomeAudit(DurableStateStore(db))
        assert restarted.get("m1", "g3", "production")["status"] == "completed"


def test_failed_step_rolls_back_and_stops_later_environment():
    touched = []
    first = _step("g1", "sandbox", ok=False, evidence=())
    second = MissionStep(
        "g2", "production", "mission-step", ActionRisk.MODERATE, True, ("plan-evidence",),
        execute=lambda: (touched.append("production") or True, ("should-not-run",)),
        rollback=lambda: True,
    )
    with TemporaryDirectory() as tmp:
        run = BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp) / "omega.db"))).run("m2", (first, second))
    assert not run.completed and run.attempted == 1 and run.recovered == 1
    assert run.outcomes[0].status == "rolled_back"
    assert touched == []


def test_kernel_denial_blocks_execution():
    touched = []
    denied = MissionStep(
        "unsafe", "production", "outside-envelope", ActionRisk.MODERATE, True, ("plan-evidence",),
        execute=lambda: (touched.append("executed") or True, ("bad",)),
        rollback=lambda: True,
    )
    kernel = MissionKernel(OperationalEnvelope(frozenset({"mission-step"}), max_risk=2, min_evidence=1))
    with TemporaryDirectory() as tmp:
        run = BoundedMissionRunner(
            OutcomeAudit(DurableStateStore(Path(tmp) / "omega.db")), mission_kernel=kernel
        ).run("m3", (denied,))
    assert not run.completed and run.outcomes[0].status == "blocked"
    assert touched == []


def test_improvement_sandbox_canary_failure_rolls_back_to_champion():
    sandbox = ImprovementSandbox()
    decision = sandbox.choose(
        CandidateScore("champion", 0.8, 1.0, True),
        CandidateScore("challenger", 0.9, 1.0, True),
    )
    assert decision.promote
    rollback = sandbox.canary(decision, lambda: False)
    assert not rollback.promote and rollback.selected == "champion"
