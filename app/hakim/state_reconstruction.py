"""ΩL6 canonical-state reconstruction and diverse assurance primitives."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path

from .durable_state import DurableStateStore


class VerificationVerdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceView:
    source: str
    subject: str
    value: object
    strength: float = 1.0

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.subject.strip():
            raise ValueError("source and subject are required")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be in [0,1]")


@dataclass(frozen=True)
class CanonicalState:
    subject: str
    value: object
    sources: tuple[str, ...]
    digest: str
    conflict: bool


class CanonicalStateReconstructor:
    """Rebuild canonical mission facts from independent durable evidence views.

    Reconstruction is fail-closed: equally strong disagreement is surfaced as a
    conflict rather than silently choosing one source.
    """

    def reconstruct(self, subject: str, evidence: tuple[EvidenceView, ...]) -> CanonicalState:
        relevant = [item for item in evidence if item.subject == subject]
        if not relevant:
            raise RuntimeError(f"no evidence for subject: {subject}")
        strongest = max(item.strength for item in relevant)
        winners = [item for item in relevant if item.strength == strongest]
        encoded = {json.dumps(item.value, sort_keys=True, ensure_ascii=False, default=str) for item in winners}
        conflict = len(encoded) > 1
        value = None if conflict else winners[0].value
        material = json.dumps(
            {"subject": subject, "value": value, "sources": sorted(item.source for item in relevant), "conflict": conflict},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return CanonicalState(
            subject=subject,
            value=value,
            sources=tuple(sorted({item.source for item in relevant})),
            digest=sha256(material.encode("utf-8")).hexdigest(),
            conflict=conflict,
        )


@dataclass(frozen=True)
class VerificationOpinion:
    verifier: str
    verdict: VerificationVerdict
    evidence_digest: str


@dataclass(frozen=True)
class AssuranceDecision:
    allowed: bool
    reason: str
    opinions: tuple[VerificationOpinion, ...]


class DiverseVerifier:
    """Requires independent verifier agreement for consequential claims."""

    def decide(self, opinions: tuple[VerificationOpinion, ...], *, consequential: bool = True) -> AssuranceDecision:
        if not opinions:
            return AssuranceDecision(False, "no verification opinions", ())
        names = {item.verifier for item in opinions}
        if consequential and len(names) < 2:
            return AssuranceDecision(False, "insufficient verifier diversity", opinions)
        verdicts = {item.verdict for item in opinions}
        if VerificationVerdict.REJECT in verdicts:
            return AssuranceDecision(False, "independent verifier rejected claim", opinions)
        if VerificationVerdict.UNKNOWN in verdicts:
            return AssuranceDecision(False, "verification uncertainty is fail-closed", opinions)
        digests = {item.evidence_digest for item in opinions}
        if consequential and len(digests) < 2:
            return AssuranceDecision(False, "verifiers are not evidence-diverse", opinions)
        return AssuranceDecision(True, "independent diverse verification accepted", opinions)


class DurableStateEvidence:
    """Extract reconstruction evidence from sovereign durable state after restart."""

    def __init__(self, store: DurableStateStore):
        self.store = store

    def state_view(self, key: str, *, source: str = "durable-state", strength: float = 1.0) -> EvidenceView:
        value = self.store.get_state(key, None)
        if value is None:
            raise RuntimeError(f"missing durable state: {key}")
        return EvidenceView(source, key, value, strength)

    def event_view(self, event_id: str, *, strength: float = 1.0) -> EvidenceView:
        matches = [event for event in self.store.all_events() if event.event_id == event_id]
        if not matches:
            raise RuntimeError(f"missing event evidence: {event_id}")
        event = matches[0]
        return EvidenceView(
            "event-log",
            f"event:{event_id}",
            {"type": event.event_type, "subject": event.subject, "payload": event.payload, "processed": event.processed},
            strength,
        )


def checkpoint_view(path: str | Path, subject: str, *, strength: float = 0.9) -> EvidenceView:
    checkpoint = Path(path)
    if not checkpoint.is_file():
        raise RuntimeError(f"checkpoint missing: {checkpoint}")
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    return EvidenceView("checkpoint", subject, payload, strength)
