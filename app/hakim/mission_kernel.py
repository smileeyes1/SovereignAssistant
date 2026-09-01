"""Deterministic safety and mission kernel for Ω APEX.

This layer is intentionally model-independent. It owns mission phase, operational
limits, authority gates and fail-closed transitions so probabilistic planners and
agents cannot redefine the safety envelope at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MissionPhase(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    DEGRADED = "degraded"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class AuthorityLevel(int, Enum):
    OBSERVE = 0
    REVERSIBLE = 1
    MODERATE = 2
    CONSEQUENTIAL = 3


@dataclass(frozen=True)
class OperationalEnvelope:
    allowed_capabilities: frozenset[str]
    max_risk: int = 2
    require_reversible_above: int = 1
    min_evidence: int = 1

    def __post_init__(self) -> None:
        if not self.allowed_capabilities:
            raise ValueError("allowed_capabilities cannot be empty")
        if not 0 <= self.max_risk <= 3:
            raise ValueError("max_risk must be in [0,3]")
        if self.min_evidence < 0:
            raise ValueError("min_evidence cannot be negative")


@dataclass(frozen=True)
class MissionAction:
    name: str
    capability: str
    risk: int
    reversible: bool
    authority: AuthorityLevel
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.capability.strip():
            raise ValueError("action name and capability are required")
        if not 0 <= self.risk <= 3:
            raise ValueError("risk must be in [0,3]")


@dataclass(frozen=True)
class KernelDecision:
    allowed: bool
    reason: str
    next_phase: MissionPhase
    degraded: bool = False


class MissionKernel:
    """Small deterministic control kernel with explicit state transitions."""

    _TRANSITIONS = {
        MissionPhase.IDLE: {MissionPhase.PLANNING, MissionPhase.BLOCKED},
        MissionPhase.PLANNING: {MissionPhase.EXECUTING, MissionPhase.BLOCKED, MissionPhase.DEGRADED},
        MissionPhase.EXECUTING: {MissionPhase.VERIFYING, MissionPhase.RECOVERING, MissionPhase.DEGRADED, MissionPhase.BLOCKED},
        MissionPhase.VERIFYING: {MissionPhase.COMPLETED, MissionPhase.RECOVERING, MissionPhase.DEGRADED, MissionPhase.BLOCKED},
        MissionPhase.RECOVERING: {MissionPhase.EXECUTING, MissionPhase.VERIFYING, MissionPhase.DEGRADED, MissionPhase.BLOCKED},
        MissionPhase.DEGRADED: {MissionPhase.EXECUTING, MissionPhase.VERIFYING, MissionPhase.RECOVERING, MissionPhase.BLOCKED, MissionPhase.COMPLETED},
        MissionPhase.COMPLETED: set(),
        MissionPhase.BLOCKED: {MissionPhase.PLANNING, MissionPhase.RECOVERING},
    }

    def __init__(self, envelope: OperationalEnvelope, phase: MissionPhase = MissionPhase.IDLE):
        self.envelope = envelope
        self.phase = phase

    def transition(self, target: MissionPhase) -> MissionPhase:
        if target not in self._TRANSITIONS[self.phase]:
            raise RuntimeError(f"invalid mission transition: {self.phase.value}->{target.value}")
        self.phase = target
        return self.phase

    def evaluate(self, action: MissionAction, *, human_approved: bool = False) -> KernelDecision:
        allowed = self.envelope.allowed_capabilities
        if "*" not in allowed and action.capability not in allowed:
            return KernelDecision(False, "capability outside operational envelope", MissionPhase.DEGRADED, True)
        if action.risk > self.envelope.max_risk:
            return KernelDecision(False, "risk exceeds operational envelope", MissionPhase.BLOCKED)
        if action.risk > self.envelope.require_reversible_above and not action.reversible:
            return KernelDecision(False, "irreversible action exceeds reversibility threshold", MissionPhase.BLOCKED)
        if len(tuple(x for x in action.evidence if str(x).strip())) < self.envelope.min_evidence:
            return KernelDecision(False, "insufficient execution evidence", MissionPhase.RECOVERING)
        if action.authority >= AuthorityLevel.CONSEQUENTIAL and not human_approved:
            return KernelDecision(False, "human authority gate required", MissionPhase.BLOCKED)
        return KernelDecision(True, "within envelope and authority", MissionPhase.EXECUTING)

    def choose_fallback(self, actions: Iterable[MissionAction], *, human_approved: bool = False) -> MissionAction | None:
        candidates: list[tuple[int, int, MissionAction]] = []
        for action in actions:
            decision = self.evaluate(action, human_approved=human_approved)
            if decision.allowed:
                candidates.append((action.risk, -len(action.evidence), action))
        return sorted(candidates, key=lambda item: (item[0], item[1], item[2].name))[0][2] if candidates else None
