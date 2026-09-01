"""ΩL5 survival control: durable FDIR and safe degraded operation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .durable_state import DurableStateStore


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    CAPABILITY_LOSS = "capability_loss"
    STATE_CORRUPTION = "state_corruption"
    SAFETY_VIOLATION = "safety_violation"


class OperatingMode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class FDIRDecision:
    component: str
    failure_class: FailureClass
    mode: OperatingMode
    isolated: bool
    recovery: str
    fallback: str | None


class SurvivalController:
    """Classifies faults, isolates unsafe components and persists recovery state.

    This controller never turns an unsafe or state-corruption condition into a
    permissive degraded mode. Degradation is allowed only when an explicitly
    supplied fallback exists and the fault class is capability loss/transient.
    """

    PREFIX = "omega.survival"

    def __init__(self, state: DurableStateStore):
        self.state = state

    def _key(self, component: str) -> str:
        return f"{self.PREFIX}.component.{component}"

    def diagnose(
        self,
        component: str,
        failure_class: FailureClass,
        *,
        fallback: str | None = None,
    ) -> FDIRDecision:
        if not component.strip():
            raise ValueError("component is required")
        if failure_class in {FailureClass.SAFETY_VIOLATION, FailureClass.STATE_CORRUPTION}:
            decision = FDIRDecision(component, failure_class, OperatingMode.BLOCKED, True, "fail-closed", None)
        elif fallback and fallback.strip():
            decision = FDIRDecision(component, failure_class, OperatingMode.DEGRADED, True, "failover", fallback.strip())
        else:
            decision = FDIRDecision(component, failure_class, OperatingMode.BLOCKED, True, "await-capability", None)
        self.state.set_state(
            self._key(component),
            {
                "failure_class": decision.failure_class.value,
                "mode": decision.mode.value,
                "isolated": decision.isolated,
                "recovery": decision.recovery,
                "fallback": decision.fallback,
            },
        )
        return decision

    def recover(self, component: str) -> OperatingMode:
        if not component.strip():
            raise ValueError("component is required")
        self.state.set_state(
            self._key(component),
            {
                "failure_class": None,
                "mode": OperatingMode.NORMAL.value,
                "isolated": False,
                "recovery": "healthy-signal",
                "fallback": None,
            },
        )
        return OperatingMode.NORMAL

    def status(self, component: str) -> dict[str, object]:
        value = self.state.get_state(self._key(component), {})
        return dict(value) if isinstance(value, dict) else {}
