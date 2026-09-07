from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.core import ActionRisk
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import BoundedMissionRunner, MissionStep, OutcomeAudit


def _consequential_step(touched, *, ok=True):
    return MissionStep(
        "consequential",
        "production",
        "mission-step",
        ActionRisk.MODERATE,
        True,
        ("plan-evidence",),
        execute=lambda: (touched.append("executed") or ok, ("result-proof",) if ok else ()),
        rollback=lambda: True,
        requires_human_approval=True,
    )


def test_same_human_approval_proof_cannot_authorize_two_consequential_steps():
    touched = []
    proof = ("human-approval:request-123",)
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        audit = OutcomeAudit(DurableStateStore(db))
        first = MissionStep(
            "g1",
            "production",
            "mission-step",
            ActionRisk.MODERATE,
            True,
            ("plan-evidence",),
            execute=lambda: (touched.append("g1") or True, ("g1-result",)),
            rollback=lambda: True,
            requires_human_approval=True,
        )
        second = MissionStep(
            "g2",
            "production",
            "mission-step",
            ActionRisk.MODERATE,
            True,
            ("plan-evidence",),
            execute=lambda: (touched.append("g2") or True, ("g2-result",)),
            rollback=lambda: True,
            requires_human_approval=True,
        )
        run = BoundedMissionRunner(
            audit,
            approval_verifier=lambda mission_id, step: (True, proof),
        ).run("mission-one", (first, second))

    assert not run.completed
    assert touched == ["g1"]
    assert run.outcomes[0].status == "completed"
    assert run.outcomes[1].status == "blocked"
    assert run.outcomes[1].evidence == ("human approval proof already consumed",)


def test_consumed_approval_survives_restart_and_requires_fresh_proof_after_rollback():
    touched = []
    stale_proof = ("human-approval:request-stale",)
    fresh_proof = ("human-approval:request-fresh",)
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        first = BoundedMissionRunner(
            OutcomeAudit(DurableStateStore(db)),
            approval_verifier=lambda mission_id, step: (True, stale_proof),
        ).run("retry-approval", (_consequential_step(touched, ok=False),))
        assert first.outcomes[0].status == "rolled_back"

        replay = BoundedMissionRunner(
            OutcomeAudit(DurableStateStore(db)),
            approval_verifier=lambda mission_id, step: (True, stale_proof),
        ).run("retry-approval", (_consequential_step(touched, ok=True),))
        assert not replay.completed
        assert replay.outcomes[0].status == "blocked"
        assert replay.outcomes[0].evidence == ("human approval proof already consumed",)

        fresh = BoundedMissionRunner(
            OutcomeAudit(DurableStateStore(db)),
            approval_verifier=lambda mission_id, step: (True, fresh_proof),
        ).run("retry-approval", (_consequential_step(touched, ok=True),))

    assert fresh.completed
    assert touched == ["executed", "executed"]
    assert fresh.outcomes[0].evidence == ("result-proof", "human-approval:request-fresh")


def test_approval_ledger_persists_only_digest_not_raw_proof():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "omega.db"
        store = DurableStateStore(db)
        audit = OutcomeAudit(store)
        proof = ("sensitive-human-approval-token",)
        assert audit.consume_approval("m", "g", "production", proof)
        assert not audit.consume_approval("other", "g2", "production", proof)
        assert "sensitive-human-approval-token" not in db.read_bytes().decode("utf-8", errors="ignore")
