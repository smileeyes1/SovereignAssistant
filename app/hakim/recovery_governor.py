"""Governed autonomous action selection with persistent recovery/failover memory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .core import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel
from .durable_state import DurableStateStore
from .event_continuation import ActionCandidate, ContinuationEvent, EventDrivenContinuation, EventType


ClaimFactory = Callable[[ContinuationEvent], Claim]
ReadyPredicate = Callable[[ContinuationEvent], bool]
ActionExecutor = Callable[[ContinuationEvent], None]


@dataclass(frozen=True)
class RegisteredAction:
    name: str
    event_types: tuple[EventType, ...]
    value: float
    risk: ActionRisk
    reversible: bool
    requires_human_approval: bool
    claim_factory: ClaimFactory
    executor: ActionExecutor
    ready: ReadyPredicate = lambda event: True

    def governance_action(self) -> Action:
        return Action(self.name, self.risk, self.reversible, self.requires_human_approval)


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, RegisteredAction] = {}

    def register(self, action: RegisteredAction) -> None:
        if not action.name.strip():
            raise ValueError("action name is required")
        if action.name in self._actions:
            raise ValueError(f"duplicate action: {action.name}")
        self._actions[action.name] = action

    def get(self, name: str) -> RegisteredAction:
        return self._actions[name]

    def matching(self, event: ContinuationEvent) -> Iterable[RegisteredAction]:
        return (a for a in self._actions.values() if event.event_type in a.event_types)


class RecoveryGovernor:
    """Selects the highest-value governed path and abandons repeatedly failing paths."""

    FAILURE_PREFIX = "omega.recovery.failures"

    def __init__(self, registry: ActionRegistry, state: DurableStateStore, governance: GovernanceKernel | None = None, max_failures_per_path: int = 2):
        if max_failures_per_path < 1:
            raise ValueError("max_failures_per_path must be positive")
        self.registry = registry
        self.state = state
        self.governance = governance or GovernanceKernel()
        self.max_failures_per_path = max_failures_per_path

    def _key(self, event_id: str, action_name: str) -> str:
        return f"{self.FAILURE_PREFIX}.{event_id}.{action_name}"

    def failure_count(self, event_id: str, action_name: str) -> int:
        return int(self.state.get_state(self._key(event_id, action_name), 0))

    def _record_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), self.failure_count(event_id, action_name) + 1)

    def _clear_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), 0)

    def candidates(self, event: ContinuationEvent) -> list[ActionCandidate]:
        candidates: list[ActionCandidate] = []
        for registered in self.registry.matching(event):
            if self.failure_count(event.event_id, registered.name) >= self.max_failures_per_path:
                continue
            claim = registered.claim_factory(event)
            decision = self.governance.evaluate(claim, registered.governance_action())
            candidates.append(
                ActionCandidate(
                    registered.name,
                    registered.value,
                    safe=decision == Decision.PROCEED,
                    reversible=registered.reversible,
                    authorized=decision == Decision.PROCEED,
                    ready=registered.ready(event),
                )
            )
        return candidates

    def execute(self, candidate: ActionCandidate, event: ContinuationEvent) -> None:
        action = self.registry.get(candidate.name)
        try:
            action.executor(event)
        except Exception:
            self._record_failure(event.event_id, action.name)
            raise
        self._clear_failure(event.event_id, action.name)

    def engine(self) -> EventDrivenContinuation:
        return EventDrivenContinuation(self.candidates, self.execute)


def strong_claim(statement: str, source: str = "runtime") -> Claim:
    """Convenience for deterministic, directly observed operational evidence."""
    return Claim(statement, (Evidence(source, statement, 1.0),), confidence=1.0)
