"""Durable capability/provider health registry for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .durable_state import DurableStateStore


@dataclass(frozen=True)
class CapabilityHealth:
    name: str
    healthy: bool
    failures: int
    last_error: str | None
    updated_at: str


class CapabilityRegistry:
    PREFIX = "omega.capability.v1."

    def __init__(self, state: DurableStateStore, failure_threshold: int = 2):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        self.state = state
        self.failure_threshold = failure_threshold

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _key(self, name: str) -> str:
        if not name.strip():
            raise ValueError("capability name is required")
        return self.PREFIX + name

    def get(self, name: str) -> CapabilityHealth:
        raw = self.state.get_state(self._key(name))
        if not isinstance(raw, dict):
            return CapabilityHealth(name, True, 0, None, self._now())
        return CapabilityHealth(
            name=name,
            healthy=bool(raw.get("healthy", True)),
            failures=int(raw.get("failures", 0)),
            last_error=None if raw.get("last_error") is None else str(raw.get("last_error")),
            updated_at=str(raw.get("updated_at", self._now())),
        )

    def record_failure(self, name: str, error: str) -> CapabilityHealth:
        current = self.get(name)
        failures = current.failures + 1
        health = CapabilityHealth(name, failures < self.failure_threshold, failures, error, self._now())
        self._save(health)
        return health

    def record_success(self, name: str) -> CapabilityHealth:
        health = CapabilityHealth(name, True, 0, None, self._now())
        self._save(health)
        return health

    def is_healthy(self, name: str) -> bool:
        return self.get(name).healthy

    def _save(self, health: CapabilityHealth) -> None:
        self.state.set_state(
            self._key(health.name),
            {
                "healthy": health.healthy,
                "failures": health.failures,
                "last_error": health.last_error,
                "updated_at": health.updated_at,
            },
        )
