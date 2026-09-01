"""ΩL7 bounded mission autonomy controls.

These primitives are deterministic and conservative. Every executable mission
step is evaluated by GovernanceKernel and then MissionKernel before its callback
may run. Outcome audit, champion/challenger admission, canary rollback and
bounded multi-environment progression remain inside the declared envelope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .core import Action, ActionRisk, Claim, Decision, Evidence, GovernanceKernel
from .durable_state import DurableStateStore
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope


@dataclass(frozen=True)
class OutcomeRecord:
    mission_id: str
    goal_id: str
    environment: str
    status: str
    evidence: tuple[str, ...]
    rollback: bool = False


class OutcomeAudit:
    PREFIX = "omega.outcomes"

    def __init__(self, state: DurableStateStore):
        self.state = state

    def record(self, item: OutcomeRecord) -> None:
        if not item.mission_id.strip() or not item.goal_id.strip() or not item.environment.strip():
            raise ValueError("mission_id, goal_id and environment are required")
        if item.status not in {"completed", "failed", "rolled_back", "blocked"}:
            raise ValueError("invalid outcome status")
        if item.status == "completed" and not item.evidence:
            raise ValueError("completed outcomes require evidence")
        self.state.set_state(
            f"{self.PREFIX}.{item.mission_id}.{item.goal_id}.{item.environment}",
            {
                "mission_id": item.mission_id,
                "goal_id": item.goal_id,
                "environment": item.environment,
                "status": item.status,
                "evidence": list(item.evidence),
                "rollback": item.rollback,
            },
        )

    def get(self, mission_id: str, goal_id: str, environment: str) -> dict[str, object]:
        value = self.state.get_state(f"{self.PREFIX}.{mission_id}.{goal_id}.{environment}", {})
        return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class CandidateScore:
    name: str
    quality: float
    safety: float
    regression_passed: bool


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    selected: str
    reason: str


class ImprovementSandbox:
    """Champion/challenger admission with fail-closed canary rollback semantics."""

    def choose(self, champion: CandidateScore, challenger: CandidateScore) -> PromotionDecision:
        if not challenger.regression_passed:
            return PromotionDecision(False, champion.name, "challenger regression failed")
        if challenger.safety < champion.safety:
            return PromotionDecision(False, champion.name, "challenger safety regressed")
        if challenger.quality <= champion.quality:
            return PromotionDecision(False, champion.name, "challenger has no quality gain")
        return PromotionDecision(True, challenger.name, "challenger dominated champion")

    def canary(self, decision: PromotionDecision, probe: Callable[[], bool]) -> PromotionDecision:
        if not decision.promote:
            return decision
        try:
            passed = bool(probe())
        except Exception:
            passed = False
        if not passed:
            return PromotionDecision(False, "champion", "canary failed; rollback required")
        return decision


_RISK_SCORE = {
    ActionRisk.LOW: 0,
    ActionRisk.MODERATE: 1,
    ActionRisk.HIGH: 2,
    ActionRisk.CRITICAL: 3,
}


@dataclass(frozen=True)
class MissionStep:
    goal_id: str
    environment: str
    capability: str
    risk: ActionRisk
    reversible: bool
    evidence: tuple[str, ...]
    execute: Callable[[], tuple[bool, tuple[str, ...]]]
    rollback: Callable[[], bool]
    requires_human_approval: bool = False


@dataclass(frozen=True)
class MissionRun:
    completed: bool
    attempted: int
    recovered: int
    outcomes: tuple[OutcomeRecord, ...]


class BoundedMissionRunner:
    """Runs bounded multi-environment work only after both Golden Baseline gates."""

    def __init__(
        self,
        audit: OutcomeAudit,
        *,
        governance: GovernanceKernel | None = None,
        mission_kernel: MissionKernel | None = None,
    ):
        self.audit = audit
        self.governance = governance or GovernanceKernel()
        self.mission_kernel = mission_kernel or MissionKernel(
            OperationalEnvelope(frozenset({"mission-step"}), max_risk=2, require_reversible_above=1, min_evidence=1)
        )

    def _authorized(self, step: MissionStep) -> bool:
        claim = Claim(
            f"mission step {step.goal_id} in {step.environment} is ready",
            tuple(Evidence("mission-plan", item, 1.0) for item in step.evidence if item.strip()),
            confidence=1.0 if step.evidence else 0.0,
        )
        action = Action(
            step.goal_id,
            step.risk,
            reversible=step.reversible,
            requires_human_approval=step.requires_human_approval,
        )
        if self.governance.evaluate(claim, action) != Decision.PROCEED:
            return False
        mission = MissionAction(
            name=step.goal_id,
            capability=step.capability,
            risk=_RISK_SCORE[step.risk],
            reversible=step.reversible,
            authority=AuthorityLevel.CONSEQUENTIAL if step.requires_human_approval else AuthorityLevel.MODERATE,
            evidence=step.evidence,
        )
        return self.mission_kernel.evaluate(mission, human_approved=False).allowed

    def run(self, mission_id: str, steps: Iterable[MissionStep]) -> MissionRun:
        outcomes: list[OutcomeRecord] = []
        recovered = 0
        attempted = 0
        for step in steps:
            attempted += 1
            if not self._authorized(step):
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "blocked", step.evidence, False)
                self.audit.record(record)
                outcomes.append(record)
                return MissionRun(False, attempted, recovered, tuple(outcomes))
            try:
                ok, result_evidence = step.execute()
            except Exception:
                ok, result_evidence = False, ()
            if ok and result_evidence:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "completed", tuple(result_evidence), False)
                self.audit.record(record)
                outcomes.append(record)
                continue
            rollback_ok = False
            try:
                rollback_ok = bool(step.rollback())
            except Exception:
                rollback_ok = False
            if rollback_ok:
                recovered += 1
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "rolled_back", tuple(result_evidence), True)
            else:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "failed", tuple(result_evidence), False)
            self.audit.record(record)
            outcomes.append(record)
            return MissionRun(False, attempted, recovered, tuple(outcomes))
        return MissionRun(bool(outcomes), attempted, recovered, tuple(outcomes))
