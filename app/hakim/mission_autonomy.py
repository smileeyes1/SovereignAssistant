"""ΩL7 bounded mission autonomy controls.

These primitives are deterministic and intentionally conservative: they provide
outcome audit, champion/challenger admission, canary rollback, and bounded
multi-environment mission progression without bypassing the existing kernels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .durable_state import DurableStateStore


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
        if item.status not in {"completed", "failed", "rolled_back"}:
            raise ValueError("invalid outcome status")
        if item.status == "completed" and not item.evidence:
            raise ValueError("completed outcomes require evidence")
        key = f"{self.PREFIX}.{item.mission_id}.{item.goal_id}.{item.environment}"
        self.state.set_state(
            key,
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


@dataclass(frozen=True)
class MissionStep:
    goal_id: str
    environment: str
    execute: Callable[[], tuple[bool, tuple[str, ...]]]
    rollback: Callable[[], bool]


@dataclass(frozen=True)
class MissionRun:
    completed: bool
    attempted: int
    recovered: int
    outcomes: tuple[OutcomeRecord, ...]


class BoundedMissionRunner:
    """Runs a declared mission plan across environments with explicit rollback.

    A failed step is rolled back and the mission stops; no later environment is
    entered after a failed recovery. This is a deterministic operational-envelope
    harness, not permission to bypass GovernanceKernel or MissionKernel.
    """

    def __init__(self, audit: OutcomeAudit):
        self.audit = audit

    def run(self, mission_id: str, steps: Iterable[MissionStep]) -> MissionRun:
        outcomes: list[OutcomeRecord] = []
        recovered = 0
        attempted = 0
        for step in steps:
            attempted += 1
            try:
                ok, evidence = step.execute()
            except Exception:
                ok, evidence = False, ()
            if ok and evidence:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "completed", tuple(evidence), False)
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
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "rolled_back", tuple(evidence), True)
            else:
                record = OutcomeRecord(mission_id, step.goal_id, step.environment, "failed", tuple(evidence), False)
            self.audit.record(record)
            outcomes.append(record)
            return MissionRun(False, attempted, recovered, tuple(outcomes))
        return MissionRun(bool(outcomes), attempted, recovered, tuple(outcomes))
