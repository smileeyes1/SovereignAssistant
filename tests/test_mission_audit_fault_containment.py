from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import BoundedMissionRunner, MissionStep, OutcomeAudit, OutcomeRecord


class ReadFaultAudit(OutcomeAudit):
    def get(self, mission_id: str, goal_id: str, environment: str):
        raise OSError("injected outcome-read fault")


class CompletedWriteFaultAudit(OutcomeAudit):
    def record(self, item: OutcomeRecord) -> None:
        if item.status == "completed":
            raise OSError("injected completed-outcome write fault")
        super().record(item)


def _successful_step(touched: list[str]) -> MissionStep:
    return MissionStep(
        "g1",
        "production",
        "mission-step",
        ActionRisk.MODERATE,
        True,
        ("plan-evidence",),
        execute=lambda: (touched.append("executed") or True, ("result-proof",)),
        rollback=lambda: True,
    )


def test_outcome_read_fault_fails_closed_before_side_effect():
    touched: list[str] = []
    with TemporaryDirectory() as tmp:
        audit = ReadFaultAudit(DurableStateStore(Path(tmp) / "omega.db"))
        run = BoundedMissionRunner(audit).run("read-fault", (_successful_step(touched),))

    assert not run.completed
    assert run.outcomes[0].status == "blocked"
    assert "no side effect executed" in run.outcomes[0].evidence[-1]
    assert touched == []


def test_completed_outcome_write_fault_is_contained_and_replay_stays_blocked():
    touched: list[str] = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        first = BoundedMissionRunner(CompletedWriteFaultAudit(DurableStateStore(db))).run(
            "write-fault", (_successful_step(touched),)
        )
        second = BoundedMissionRunner(OutcomeAudit(DurableStateStore(db))).run(
            "write-fault", (_successful_step(touched),)
        )

    assert not first.completed
    assert first.outcomes[0].status == "blocked"
    assert "side effect succeeded" in first.outcomes[0].evidence[-1]
    assert not second.completed
    assert second.outcomes[0].status == "blocked"
    assert "reservation already exists" in second.outcomes[0].evidence[-1]
    assert touched == ["executed"]
