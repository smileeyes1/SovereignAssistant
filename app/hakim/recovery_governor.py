"""Governed autonomous action selection with persistent recovery/failover memory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .best_route_optimizer import RouteInput, RouteOptimizationContext, RouteProfile, optimize_routes
from .core import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel
from .durable_state import DurableStateStore
from .event_continuation import ActionCandidate, ContinuationEvent, EventDrivenContinuation, EventType
from .intelligence_fabric import IntelligenceRequest, RiskTier, composition_plan, select_intelligence
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
    route_profile: RouteProfile = RouteProfile()

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

_RISK_TIER = {
    ActionRisk.LOW: RiskTier.LOW,
    ActionRisk.MODERATE: RiskTier.MEDIUM,
    ActionRisk.HIGH: RiskTier.HIGH,
    ActionRisk.CRITICAL: RiskTier.CRITICAL,
}

_EVENT_INTELLIGENCE_SIGNALS = {
    EventType.CI_SUCCEEDED: frozenset({"facts", "test", "acceptance", "regression"}),
    EventType.CI_FAILED: frozenset({"facts", "failure", "repair", "root_cause", "single_path_failure", "test"}),
    EventType.PR_MERGED: frozenset({"facts", "integration", "regression", "release", "system"}),
    EventType.TASK_COMPLETED: frozenset({"facts", "acceptance", "state", "reuse"}),
    EventType.TASK_FAILED: frozenset({"facts", "failure", "repair", "root_cause", "single_path_failure"}),
    EventType.CHECKPOINT_SAVED: frozenset({"state", "history", "reuse", "persistent"}),
    EventType.CAPABILITY_CHANGED: frozenset({"facts", "system", "integration", "dependencies"}),
    EventType.MANUAL_SIGNAL: frozenset({"intent", "ambiguity", "context"}),
}


class RecoveryGovernor:
    """Selects the best eligible path under governance, evidence and constraints.

    Authorization is deliberately evaluated twice: once while selecting a
    candidate and again immediately before the real executor is invoked. The
    execution-time check is the final fail-closed boundary against stale,
    forged, or time-of-check/time-of-use candidates.

    The intelligence fabric is also routed twice. The selection route records
    what intelligence families are required before candidate choice. The
    execution-boundary route is recomputed immediately before authorization and
    side effects. Routing is evidence that the fabric was invoked, not evidence
    that every named reasoning method was actually executed.

    Candidate ranking is multi-criteria: base outcome value is only one input.
    The optimizer also weighs fit, evidence, expected success, safety, burden,
    cost, dependency, independence, sustainability, speed, reversibility and
    prior failures. The ranking is persisted for audit and must not be described
    as proof that a route will succeed.
    """

    FAILURE_PREFIX = "omega.recovery.failures"
    INTELLIGENCE_PREFIX = "omega.intelligence_fabric.route"
    BEST_ROUTE_PREFIX = "omega.best_route.assessment"

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

    def _intelligence_key(self, event_id: str, stage: str) -> str:
        return f"{self.INTELLIGENCE_PREFIX}.{stage}.{event_id}"

    def _best_route_key(self, event_id: str, stage: str) -> str:
        return f"{self.BEST_ROUTE_PREFIX}.{stage}.{event_id}"

    def failure_count(self, event_id: str, action_name: str) -> int:
        return int(self.state.get_state(self._key(event_id, action_name), 0))

    def _record_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), self.failure_count(event_id, action_name) + 1)

    def _clear_failure(self, event_id: str, action_name: str) -> None:
        self.state.set_state(self._key(event_id, action_name), 0)

    @staticmethod
    def _payload_signals(event: ContinuationEvent) -> set[str]:
        raw = event.payload.get("intelligence_signals", event.payload.get("signals", ()))
        if isinstance(raw, str):
            raw = (raw,)
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return set()
        signals: set[str] = set()
        for item in tuple(raw)[:32]:
            if not isinstance(item, str):
                continue
            signal = item.strip().lower().replace("-", "_").replace(" ", "_")
            if signal and len(signal) <= 64:
                signals.add(signal)
        return signals

    @staticmethod
    def _payload_uncertainty(event: ContinuationEvent) -> float:
        raw = event.payload.get("uncertainty")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            if event.event_type in {EventType.CI_FAILED, EventType.TASK_FAILED}:
                return 0.35
            if event.event_type == EventType.MANUAL_SIGNAL:
                return 0.50
            return 0.10
        return max(0.0, min(1.0, float(raw)))

    def _intelligence_request(
        self,
        event: ContinuationEvent,
        actions: Iterable[RegisteredAction],
    ) -> IntelligenceRequest:
        items = tuple(actions)
        risk = max((_RISK_TIER[item.risk] for item in items), default=RiskTier.LOW)
        signals = {
            "intent", "context", "action", "execution", "state", "persistent",
            *_EVENT_INTELLIGENCE_SIGNALS.get(event.event_type, frozenset()),
            *self._payload_signals(event),
        }
        claimed_improvement = bool(event.payload.get("claimed_improvement", False)) or (
            event.payload.get("source") == "continuous-excellence"
        )
        return IntelligenceRequest(
            signals=frozenset(signals),
            risk=risk,
            uncertainty=self._payload_uncertainty(event),
            requires_execution=True,
            persistent=True,
            claimed_improvement=claimed_improvement,
        )

    def _route_intelligence(
        self,
        event: ContinuationEvent,
        actions: Iterable[RegisteredAction],
        *,
        stage: str,
    ) -> dict[str, object]:
        request = self._intelligence_request(event, actions)
        selected = select_intelligence(request)
        selected_names = {item.family for item in selected}
        required = {"intent_contract", "metacognitive", "simplicity_economy", "operational_execution", "memory_learning"}
        if request.risk >= RiskTier.HIGH:
            required.update({"evidence", "adversarial", "decision_strategy", "security_privacy"})
        if request.risk >= RiskTier.CRITICAL:
            required.add("ensemble")
        if request.uncertainty >= 0.60:
            required.update({"evidence", "probabilistic"})
        missing = sorted(required - selected_names)
        if missing:
            raise RuntimeError("intelligence fabric mandatory guards missing: " + ", ".join(missing))

        route: dict[str, object] = {
            "status": "ROUTED_NOT_METHOD_EXECUTION_PROOF",
            "stage": stage,
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "subject": event.subject,
            "request": {
                "signals": sorted(request.signals),
                "risk": int(request.risk),
                "uncertainty": request.uncertainty,
                "requires_execution": request.requires_execution,
                "persistent": request.persistent,
                "claimed_improvement": request.claimed_improvement,
            },
            "selected": [
                {
                    "family": item.family,
                    "methods": list(item.methods),
                    "score": item.score,
                    "reasons": list(item.reasons),
                    "mandatory": item.mandatory,
                }
                for item in selected
            ],
            "composition": list(composition_plan(request)),
        }
        self.state.set_state(self._intelligence_key(event.event_id, stage), route)
        return route

    def intelligence_route(self, event_id: str, stage: str = "execution") -> dict[str, object] | None:
        raw = self.state.get_state(self._intelligence_key(event_id, stage))
        return dict(raw) if isinstance(raw, dict) else None

    def _rank_routes(
        self,
        event: ContinuationEvent,
        actions: Iterable[RegisteredAction],
        *,
        stage: str,
    ) -> dict[str, float]:
        items = tuple(actions)
        assessments = optimize_routes(
            (
                RouteInput(
                    name=item.name,
                    base_value=item.value,
                    risk=_RISK_SCORE[item.risk],
                    reversible=item.reversible,
                    requires_human_approval=item.requires_human_approval,
                    failure_count=self.failure_count(event.event_id, item.name),
                    profile=item.route_profile,
                )
                for item in items
            ),
            RouteOptimizationContext(
                uncertainty=self._payload_uncertainty(event),
                zero_paid_cost=bool(event.payload.get("zero_paid_cost", False)),
            ),
        )
        audit: dict[str, object] = {
            "status": "RANKED_NOT_OUTCOME_PROOF",
            "stage": stage,
            "event_id": event.event_id,
            "criteria": [
                "outcome_value", "context_fit", "evidence", "expected_success",
                "safety", "burden", "cost", "external_dependency", "independence",
                "sustainability", "speed", "reversibility", "prior_failures", "pareto_dominance",
            ],
            "winner": assessments[0].name if assessments else None,
            "assessments": [
                {
                    "name": item.name,
                    "score": item.score,
                    "dominated": item.dominated,
                    "components": item.components,
                    "route": item.route,
                    "reasons": list(item.reasons),
                }
                for item in assessments
            ],
        }
        self.state.set_state(self._best_route_key(event.event_id, stage), audit)
        return {item.name: item.score for item in assessments}

    def best_route_assessment(self, event_id: str, stage: str = "selection") -> dict[str, object] | None:
        raw = self.state.get_state(self._best_route_key(event_id, stage))
        return dict(raw) if isinstance(raw, dict) else None

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

        mission_decision = self._mission_decision(registered, claim)
        if not mission_decision.allowed:
            self._record_mission_denial(registered, event, mission_decision)

        if governance_decision != Decision.PROCEED:
            return False, f"governance denied: {governance_decision.value}"
        if not mission_decision.allowed:
            return False, f"mission denied: {mission_decision.reason}"
        return True, "governance and mission gates passed"

    def candidates(self, event: ContinuationEvent) -> list[ActionCandidate]:
        registered_actions = tuple(self.registry.matching(event))
        self._route_intelligence(event, registered_actions, stage="selection")
        route_scores = self._rank_routes(event, registered_actions, stage="selection")
        candidates: list[ActionCandidate] = []
        for registered in registered_actions:
            if self.failure_count(event.event_id, registered.name) >= self.max_failures_per_path:
                continue
            allowed, _ = self._authorize(registered, event)
            candidates.append(
                ActionCandidate(
                    registered.name,
                    route_scores.get(registered.name, registered.value),
                    safe=allowed,
                    reversible=registered.reversible,
                    authorized=allowed,
                    ready=registered.ready(event),
                )
            )
        return candidates

    def execute(self, candidate: ActionCandidate, event: ContinuationEvent) -> None:
        action = self.registry.get(candidate.name)

        matching = list(self.registry.matching(event))
        if all(item.name != action.name for item in matching):
            matching.append(action)
        matching_tuple = tuple(matching)
        self._route_intelligence(event, matching_tuple, stage="execution")
        self._rank_routes(event, matching_tuple, stage="execution")

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
