"""Small, deterministic governance kernel for HAKIM Ω.

The kernel deliberately does not call models or tools. It decides whether a
proposed action is sufficiently supported to proceed and whether approval is
required. Provider/tool execution belongs in adapters outside this module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ActionRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(str, Enum):
    PROCEED = "proceed"
    APPROVAL_REQUIRED = "approval_required"
    BLOCK = "block"


@dataclass(frozen=True)
class Evidence:
    source: str
    statement: str
    strength: float = 1.0

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("evidence source is required")
        if not self.statement.strip():
            raise ValueError("evidence statement is required")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("evidence strength must be between 0 and 1")


@dataclass(frozen=True)
class Claim:
    statement: str
    evidence: tuple[Evidence, ...] = ()
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("claim statement is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def supported(self) -> bool:
        return bool(self.evidence) and max(e.strength for e in self.evidence) > 0.0


@dataclass(frozen=True)
class Action:
    name: str
    risk: ActionRisk
    reversible: bool = True
    requires_human_approval: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("action name is required")


@dataclass(frozen=True)
class AuditEvent:
    event: str
    decision: Decision
    action: str
    reason: str


@dataclass
class GovernanceKernel:
    min_confidence: float = 0.70
    audit_log: list[AuditEvent] = field(default_factory=list)

    def evaluate(self, claim: Claim, action: Action) -> Decision:
        """Apply the minimum governance gate before execution."""
        if not claim.supported:
            return self._record(action, Decision.BLOCK, "claim has no usable evidence")

        if claim.confidence < self.min_confidence:
            return self._record(
                action,
                Decision.BLOCK,
                "claim confidence is below the governance threshold",
            )

        approval_required = (
            action.requires_human_approval
            or action.risk in {ActionRisk.HIGH, ActionRisk.CRITICAL}
            or not action.reversible
        )
        if approval_required:
            return self._record(action, Decision.APPROVAL_REQUIRED, "consequential action")

        return self._record(action, Decision.PROCEED, "evidence and confidence gates passed")

    def _record(self, action: Action, decision: Decision, reason: str) -> Decision:
        self.audit_log.append(
            AuditEvent(
                event="decision_gate",
                decision=decision,
                action=action.name,
                reason=reason,
            )
        )
        return decision


def evidence_from(items: Iterable[Evidence]) -> tuple[Evidence, ...]:
    """Normalize evidence collections without changing their semantics."""
    return tuple(items)
