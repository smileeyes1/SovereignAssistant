"""Governed autonomous action selection with persistent recovery/failover memory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .core import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel
from .durable_state import DurableStateStore
from .event_continuation import ActionCandidate, ContinuationEvent, EventDrivenContinuation, EventType
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope


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


_RISK_SCORE = {
    ActionRisk.LOW: 0,
    ActionRisk.MODERATE: 1,
    ActionRisk.HIGH: 2,
    ActionRisk.CRITICAL: 3,
}


class RecoveryGovernor:
    """Selects the highest-value path allowed by governance and mission safety.

    Authorization is deliberately evaluated twice: once while selecting a
    candidate and again immediately before the real executor is invoked. The
    execution-time check is the final fail-closed boundary against stale,
    forged, or time-of-check/time-of-use candidates.
    """

    FAILURE_PREFIX = "omega.recovery.failures"

    def __init__(
        self,
        registry: ActionRegistry,
        state: DurableStateStore,
        governance: GovernanceKernel | None = None,
        max_failures_per_path: int = 2,
        mission_kernel: MissionKernel | None = None,
    ):
        if max_failures_per_path < 1:
            raise ValueError("max_failures_per_path must be positive")
        self.registry = registry
        self.state = state
        self.governance = governance or GovernanceKernel()
        self.max_failures_per_path = max_failures_per_path
        self.mission_kernel = mission_kernel or MissionKernel(
            OperationalEnvelope(
                allowed_capabilities=frozenset({"*"}),
                max_risk=2,
                require_reversible_above=1,
                min_evidence=1,
            )
        )

    def _key(self, event_id: str, action_name: str) -> str:
        return f"{self.FAILURE_PREFIX}.{event_id}.{action_name}"

    def failure_count(self, event_id: str, action_name: str) -> int:
        return int(self.state.get_state(self._key(event_id, action_name), 0))

    def _record_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), self.failure_count(event_id, action_name) + 1)

    def _clear_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), 0)

    def _mission_decision(self, registered: RegisteredAction, claim: Claim):
        authority = AuthorityLevel.CONSEQUENTIAL if registered.requires_human_approval else AuthorityLevel.MODERATE
        action = MissionAction(
            name=registered.name,
            capability=registered.name,
            risk=_RISK_SCORE[registered.risk],
            reversible=registered.reversible,
            authority=authority,
            evidence=tuple(e.statement for e in claim.evidence),
        )
        return self.mission_kernel.evaluate(action, human_approved=False)

    def _record_mission_denial(self, registered: RegisteredAction, event: ContinuationEvent, decision) -> None:
        self.state.set_state(
            f"omega.mission_kernel.last_denial.{registered.name}",
            {
                "event_id": event.event_id,
                "reason": decision.reason,
                "next_phase": decision.next_phase.value,
            },
        )

    def _authorize(self, registered: RegisteredAction, event: ContinuationEvent) -> tuple[bool, str]:
        """Evaluate both Golden gates in strict GovernanceKernel → MissionKernel order."""
        claim = registered.claim_factory(event)
        governance_decision = self.governance.evaluate(claim, registered.governance_action())

        # Preserve independent MissionKernel enforcement and denial evidence even
        # when governance already fails; execution still requires both to pass.
        mission_decision = self._mission_decision(registered, claim)
        if not mission_decision.allowed:
            self._record_mission_denial(registered, event, mission_decision)

        if governance_decision != Decision.PROCEED:
            return False, f"governance denied: {governance_decision.value}"
        if not mission_decision.allowed:
            return False, f"mission denied: {mission_decision.reason}"
        return True, "governance and mission gates passed"

    def candidates(self, event: ContinuationEvent) -> list[ActionCandidate]:
        candidates: list[ActionCandidate] = []
        for registered in self.registry.matching(event):
            if self.failure_count(event.event_id, registered.name) >= self.max_failures_per_path:
                continue
            allowed, _ = self._authorize(registered, event)
            candidates.append(
                ActionCandidate(
                    registered.name,
                    registered.value,
                    safe=allowed,
                    reversible=registered.reversible,
                    authorized=allowed,
                    ready=registered.ready(event),
                )
            )
        return candidates

    def execute(self, candidate: ActionCandidate, event: ContinuationEvent) -> None:
        action = self.registry.get(candidate.name)

        # Selection-time authorization is not a capability token. Re-evaluate
        # both kernels at the last possible point before any real side effect.
        allowed, reason = self._authorize(action, event)
        if not allowed:
            raise PermissionError(f"execution-time authorization failed for {action.name}: {reason}")

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
