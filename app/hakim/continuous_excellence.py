"""Post-ΩL7 autonomous continuous-excellence control for Ω APEX.

A completed finite roadmap is a certified baseline, not the end of system life.
The controller observes durable runtime evidence, selects at most one verified
reversible gap per cycle, and emits governed work. It never promotes changes
directly: Mission Kernel, sandbox, benchmark, Arena/CI, canary and authority
gates remain mandatory.
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


class OperationalSignalCollector:
    """Build improvement signals only from durable, inspectable evidence."""

    OBSERVATIONS_KEY = "omega.continuous_excellence.observations"

    def __init__(self, state: DurableStateStore, queue: DurableWorkQueue):
        self.state = state
        self.queue = queue

    def collect(self) -> tuple[ImprovementSignal, ...]:
        signals: list[ImprovementSignal] = []
        with self.queue._connect() as conn:
            dead = conn.execute("SELECT COUNT(*) AS n FROM work_queue WHERE status='dead'").fetchone()
            recovered = conn.execute(
                "SELECT COUNT(*) AS n FROM work_queue WHERE status='completed' AND attempts>1"
            ).fetchone()
        dead_count = int(dead["n"])
        recovered_count = int(recovered["n"])
        if dead_count:
            signals.append(ImprovementSignal(
                "reliability",
                "eliminate durable dead-letter work",
                5,
                (f"work_queue:dead={dead_count}",),
            ))
        elif recovered_count:
            signals.append(ImprovementSignal(
                "reliability",
                "reduce repeated execution needed for successful work",
                3,
                (f"work_queue:recovered_after_retry={recovered_count}",),
            ))

        observations = self.state.get_state(self.OBSERVATIONS_KEY, [])
        if isinstance(observations, list):
            for item in observations:
                if not isinstance(item, dict):
                    continue
                evidence = item.get("evidence", [])
                if not isinstance(evidence, list):
                    continue
                signals.append(ImprovementSignal(
                    str(item.get("domain", "")),
                    str(item.get("description", "")),
                    int(item.get("severity", 0)),
                    tuple(str(x) for x in evidence),
                    bool(item.get("reversible", True)),
                ))
        return tuple(signals)


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
                    "requires_adversarial_regression": True,
                    "requires_canary": True,
                    "requires_post_promotion_measurement": True,
                    "rollback_on_regression": True,
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
