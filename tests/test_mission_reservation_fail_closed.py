from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import BoundedMissionRunner, MissionStep, OutcomeAudit


def _step(touched, *, approved=False):
    return MissionStep(
        "g1",
        "production",
        "mission-step",
        ActionRisk.MODERATE,
        True,
        ("plan-evidence",),
        execute=lambda: (touched.append("executed") or True, ("result-proof",)),
        rollback=lambda: True,
        requires_human_approval=approved,
    )


class _ClaimFailureAudit(OutcomeAudit):
    def claim_approved_execution(self, mission_id, goal_id, environment, approval_evidence):
        raise RuntimeError("simulated sqlite persistence failure")


class _ReservationFailureAudit(OutcomeAudit):
    def reserve_execution(self, mission_id, goal_id, environment):
        raise RuntimeError("simulated sqlite persistence failure")


def test_approved_execution_persistence_failure_is_blocked_before_side_effect():
    touched = []
    with TemporaryDirectory() as tmp:
        audit = _ClaimFailureAudit(DurableStateStore(Path(tmp) / "omega.db"))
        run = BoundedMissionRunner(
            audit,
            approval_verifier=lambda mission_id, step: (True, ("human-approval:proof",)),
        ).run("mission", (_step(touched, approved=True),))

    assert not run.completed
    assert touched == []
    assert run.outcomes[0].status == "blocked"
    assert run.outcomes[0].evidence == (
        "execution authority/reservation persistence unavailable; no side effect executed",
    )


def test_unapproved_execution_reservation_failure_is_blocked_before_side_effect():
    touched = []
    with TemporaryDirectory() as tmp:
        audit = _ReservationFailureAudit(DurableStateStore(Path(tmp) / "omega.db"))
        run = BoundedMissionRunner(audit).run("mission", (_step(touched),))

    assert not run.completed
    assert touched == []
    assert run.outcomes[0].status == "blocked"
    assert run.outcomes[0].evidence == (
        "execution authority/reservation persistence unavailable; no side effect executed",
    )
