from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import BoundedMissionRunner, MissionStep, OutcomeAudit


class CompensationWriteFailureAudit(OutcomeAudit):
    def mark_execution_compensated(self, mission_id: str, goal_id: str, environment: str) -> bool:
        return False


def test_rollback_does_not_claim_recovery_when_compensation_persistence_fails():
    with TemporaryDirectory() as tmp:
        audit = CompensationWriteFailureAudit(DurableStateStore(Path(tmp) / "omega.db"))
        step = MissionStep(
            "g1",
            "production",
            "mission-step",
            ActionRisk.MODERATE,
            True,
            ("plan-evidence",),
            execute=lambda: (False, ()),
            rollback=lambda: True,
        )
        run = BoundedMissionRunner(audit).run("compensation-write-failure", (step,))

    assert not run.completed
    assert run.recovered == 0
    assert run.outcomes[0].status == "blocked"
    assert run.outcomes[0].rollback is False
    assert "compensation was not persisted" in run.outcomes[0].evidence[-1]
