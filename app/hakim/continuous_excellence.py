"""Post-ΩL7 autonomous continuous-excellence control for Ω APEX.

A completed finite roadmap is a certified baseline, not the end of system life.
This controller deterministically evaluates observable improvement signals and
emits at most one governed improvement opportunity per cycle. It never promotes
changes directly: normal Mission Kernel, sandbox, Arena, CI and authority gates
remain mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable

from .durable_state import DurableStateStore
from .event_continuation import EventType
from .durable_worker import DurableWorkQueue


@dataclass(frozen=True)
class ImprovementSignal:
    domain: str
    description: str
    severity: int
    evidence: tuple[str, ...]
    reversible: bool = True

    def valid(self) -> bool:
        return bool(self.domain.strip() and self.description.strip() and self.evidence) and 0 <= self.severity <= 5


@dataclass(frozen=True)
class ExcellenceDecision:
    status: str
    event_id: str | None
    selected_domain: str | None
    reason: str


class ContinuousExcellenceController:
    """Convert verified post-baseline gaps into durable governed work."""

    STATE_KEY = "omega.continuous_excellence.last"

    def __init__(self, state: DurableStateStore, queue: DurableWorkQueue):
        self.state = state
        self.queue = queue

    @staticmethod
    def _event_id(signal: ImprovementSignal) -> str:
        material = "|".join((signal.domain, signal.description, *signal.evidence))
        return "omega-excellence-" + sha256(material.encode("utf-8")).hexdigest()[:20]

    def evaluate(self, signals: Iterable[ImprovementSignal]) -> ExcellenceDecision:
        candidates = [s for s in signals if s.valid() and s.reversible]
        candidates.sort(key=lambda s: (-s.severity, s.domain, s.description))
        now = datetime.now(timezone.utc).isoformat()
        if not candidates:
            decision = ExcellenceDecision("baseline_healthy", None, None, "no verified reversible improvement gap")
        else:
            selected = candidates[0]
            event_id = self._event_id(selected)
            created = self.queue.enqueue(
                event_id,
                EventType.MANUAL_SIGNAL.value,
                "continuous-excellence",
                {
                    "source": "continuous-excellence",
                    "domain": selected.domain,
                    "description": selected.description,
                    "severity": selected.severity,
                    "evidence": list(selected.evidence),
                    "requires_sandbox": True,
                    "requires_benchmark": True,
                    "requires_canary": True,
                },
                max_attempts=5,
            )
            decision = ExcellenceDecision(
                "improvement_enqueued" if created else "improvement_already_known",
                event_id,
                selected.domain,
                "highest-severity verified reversible gap selected",
            )
        self.state.set_state(self.STATE_KEY, {**decision.__dict__, "checked_at": now})
        return decision
