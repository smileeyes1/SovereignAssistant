"""Adversarial autonomy arena and evidence-based ΩL certification for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterable


class OmegaLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4
    L5 = 5
    L6 = 6
    L7 = 7


@dataclass(frozen=True)
class ArenaScenario:
    scenario_id: str
    category: str
    severity: int
    required_level: OmegaLevel
    probe: Callable[[], bool]

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.category.strip():
            raise ValueError("scenario_id and category are required")
        if not 1 <= self.severity <= 5:
            raise ValueError("severity must be in [1,5]")


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    passed: bool
    category: str
    severity: int
    error: str | None = None


@dataclass(frozen=True)
class ArenaReport:
    results: tuple[ScenarioResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(item.passed for item in self.results)

    @property
    def pass_rate(self) -> float:
        return 0.0 if not self.results else sum(1 for item in self.results if item.passed) / len(self.results)

    def failures(self) -> tuple[ScenarioResult, ...]:
        return tuple(item for item in self.results if not item.passed)


@dataclass(frozen=True)
class Certification:
    level: OmegaLevel
    certified: bool
    reasons: tuple[str, ...]
    evidence_count: int


class AutonomyArena:
    """Runs deterministic/adversarial probes and refuses optimistic certification."""

    def run(self, scenarios: Iterable[ArenaScenario]) -> ArenaReport:
        results: list[ScenarioResult] = []
        for scenario in scenarios:
            try:
                passed = bool(scenario.probe())
                results.append(ScenarioResult(scenario.scenario_id, passed, scenario.category, scenario.severity))
            except Exception as exc:
                results.append(
                    ScenarioResult(
                        scenario.scenario_id,
                        False,
                        scenario.category,
                        scenario.severity,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
        return ArenaReport(tuple(results))

    def certify(self, level: OmegaLevel, scenarios: Iterable[ArenaScenario], report: ArenaReport) -> Certification:
        scenario_list = list(scenarios)
        applicable = [s for s in scenario_list if s.required_level <= level]
        by_id = {result.scenario_id: result for result in report.results}
        reasons: list[str] = []
        if not applicable:
            reasons.append("no applicable evidence scenarios")
        categories = {s.category for s in applicable}
        if level >= OmegaLevel.L3 and len(categories) < 2:
            reasons.append("insufficient fault-domain diversity")
        for scenario in applicable:
            result = by_id.get(scenario.scenario_id)
            if result is None:
                reasons.append(f"missing evidence: {scenario.scenario_id}")
            elif not result.passed:
                reasons.append(f"failed scenario: {scenario.scenario_id}")
        high_severity = [s for s in applicable if s.severity >= 4]
        if level >= OmegaLevel.L4 and not high_severity:
            reasons.append("no high-severity recovery evidence")
        return Certification(level, not reasons, tuple(reasons), len(applicable))


def baseline_scenarios(
    *,
    restart_probe: Callable[[], bool],
    duplicate_event_probe: Callable[[], bool],
    provider_failover_probe: Callable[[], bool],
    unsafe_action_probe: Callable[[], bool],
) -> tuple[ArenaScenario, ...]:
    return (
        ArenaScenario("restart-continuity", "runtime", 4, OmegaLevel.L2, restart_probe),
        ArenaScenario("duplicate-event-idempotency", "events", 3, OmegaLevel.L2, duplicate_event_probe),
        ArenaScenario("provider-failover", "capability", 4, OmegaLevel.L3, provider_failover_probe),
        ArenaScenario("unsafe-action-denied", "safety", 5, OmegaLevel.L3, unsafe_action_probe),
    )
