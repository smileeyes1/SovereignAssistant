"""Free-first resource policy for autonomous provider selection.

The default is deliberately conservative: local/offline and zero-cost providers are
admitted; paid providers are blocked unless an explicit break-glass policy enables
them with a finite call budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class CostTier(str, Enum):
    LOCAL = "local"
    FREE = "free"
    UNKNOWN = "unknown"
    PAID = "paid"


_TRUE = {"1", "true", "yes", "on"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE


def _as_nonnegative_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    parsed = int(value)
    if parsed < 0:
        raise ValueError("budget values must be non-negative")
    return parsed


@dataclass(frozen=True)
class CostPolicy:
    """Govern provider cost and consumption.

    Paid access is disabled by default. Enabling it is a break-glass action and
    still requires a finite positive call budget.
    """

    allow_paid: bool = False
    max_paid_calls: int = 0
    max_failure_log_chars: int = 8_000
    max_output_tokens: int = 3_072

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "CostPolicy":
        return cls(
            allow_paid=_as_bool(env.get("OMEGA_PAID_PROVIDERS_ALLOWED"), False),
            max_paid_calls=_as_nonnegative_int(env.get("OMEGA_PAID_PROVIDER_MAX_CALLS"), 0),
            max_failure_log_chars=_as_nonnegative_int(env.get("OMEGA_PROVIDER_FAILURE_LOG_CHAR_BUDGET"), 8_000),
            max_output_tokens=_as_nonnegative_int(env.get("OMEGA_PROVIDER_MAX_OUTPUT_TOKENS"), 3_072),
        )

    def admits(self, tier: CostTier | str, *, paid_calls_used: int = 0) -> bool:
        tier = CostTier(str(tier)) if not isinstance(tier, CostTier) else tier
        if tier is not CostTier.PAID:
            return True
        return self.allow_paid and self.max_paid_calls > paid_calls_used

    @property
    def mode(self) -> str:
        if not self.allow_paid or self.max_paid_calls == 0:
            return "free-only"
        return "free-first-paid-break-glass"


COST_RANK = {
    CostTier.LOCAL: 0,
    CostTier.FREE: 1,
    CostTier.UNKNOWN: 2,
    CostTier.PAID: 3,
}
