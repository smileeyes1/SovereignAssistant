import json

import pytest

from app.hakim.durable_state import DurableStateStore
from app.hakim.state_reconstruction import (
    CanonicalStateReconstructor,
    DiverseVerifier,
    DurableStateEvidence,
    EvidenceView,
    VerificationOpinion,
    VerificationVerdict,
    checkpoint_view,
)


def test_reconstruction_uses_strongest_consistent_evidence():
    reconstructor = CanonicalStateReconstructor()
    state = reconstructor.reconstruct(
        "mission.phase",
        (
            EvidenceView("db", "mission.phase", "verifying", 1.0),
            EvidenceView("event-log", "mission.phase", "verifying", 1.0),
            EvidenceView("cache", "mission.phase", "executing", 0.4),
        ),
    )
    assert state.value == "verifying"
    assert not state.conflict
    assert set(state.sources) == {"db", "event-log", "cache"}
    assert len(state.digest) == 64


def test_equal_strength_conflict_fails_closed():
    state = CanonicalStateReconstructor().reconstruct(
        "goal.status",
        (
            EvidenceView("db", "goal.status", "completed", 1.0),
            EvidenceView("git", "goal.status", "verifying", 1.0),
        ),
    )
    assert state.conflict
    assert state.value is None


def test_diverse_verifier_requires_independent_agreement():
    verifier = DiverseVerifier()
    accepted = verifier.decide(
        (
            VerificationOpinion("deterministic-checker", VerificationVerdict.ACCEPT, "digest-a"),
            VerificationOpinion("runtime-replay", VerificationVerdict.ACCEPT, "digest-b"),
        )
    )
    assert accepted.allowed

    rejected = verifier.decide(
        (
            VerificationOpinion("deterministic-checker", VerificationVerdict.ACCEPT, "digest-a"),
            VerificationOpinion("runtime-replay", VerificationVerdict.REJECT, "digest-b"),
        )
    )
    assert not rejected.allowed


def test_verifier_refuses_common_mode_evidence():
    decision = DiverseVerifier().decide(
        (
            VerificationOpinion("checker-a", VerificationVerdict.ACCEPT, "same"),
            VerificationOpinion("checker-b", VerificationVerdict.ACCEPT, "same"),
        )
    )
    assert not decision.allowed
    assert "evidence-diverse" in decision.reason


def test_durable_state_and_event_can_be_reconstructed_after_restart(tmp_path):
    db = tmp_path / "omega.db"
    first = DurableStateStore(db)
    first.set_state("mission.phase", "recovering")
    assert first.append_event("evt-1", "task_failed", "mission", {"fault": "worker-loss"})
    assert first.mark_processed("evt-1")

    restarted = DurableStateStore(db)
    evidence = DurableStateEvidence(restarted)
    phase = evidence.state_view("mission.phase")
    event = evidence.event_view("evt-1")
    assert phase.value == "recovering"
    assert event.value["processed"] is True
    assert event.value["payload"]["fault"] == "worker-loss"


def test_checkpoint_view_recovers_external_evidence(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"goal": "g1", "status": "verifying"}), encoding="utf-8")
    view = checkpoint_view(path, "goal:g1")
    assert view.source == "checkpoint"
    assert view.value["status"] == "verifying"


def test_missing_reconstruction_evidence_is_not_guessed():
    with pytest.raises(RuntimeError):
        CanonicalStateReconstructor().reconstruct("missing", ())
