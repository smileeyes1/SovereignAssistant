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


REQUIRED_CERTIFICATION_CATEGORIES: dict[OmegaLevel, frozenset[str]] = {
    OmegaLevel.L7: frozenset(
        {
            "mission-autonomy",
            "mission-safety",
            "mission-recovery",
            "self-improvement",
            "long-duration",
        }
    ),
}


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
        level_specific = [s for s in scenario_list if s.required_level == level]
        prior = [s for s in scenario_list if s.required_level < level]
        by_id = {result.scenario_id: result for result in report.results}
        reasons: list[str] = []
        if not applicable:
            reasons.append("no applicable evidence scenarios")

        # A higher ΩL must add its own evidence. It may not inherit a certificate
        # solely from lower-level scenarios that were already sufficient before.
        if level > OmegaLevel.L0 and not level_specific:
            reasons.append(f"no level-specific evidence scenarios for {level.name}")

        categories = {s.category for s in applicable}
        level_categories = {s.category for s in level_specific}
        if level >= OmegaLevel.L3 and len(categories) < 2:
            reasons.append("insufficient fault-domain diversity")

        # Certification levels with an explicit acceptance portfolio must fail
        # closed when any governing evidence domain is absent. Diversity alone is
        # insufficient because a reduced scenario set could otherwise certify a
        # level while silently dropping one of its acceptance dimensions.
        required_categories = REQUIRED_CERTIFICATION_CATEGORIES.get(level, frozenset())
        for category in sorted(required_categories - level_categories):
            reasons.append(f"missing required {level.name} evidence category: {category}")

        # Each newly claimed level from L2 onward must introduce at least one
        # genuinely new evidence domain rather than merely relabeling a prior probe.
        if level >= OmegaLevel.L2 and level_specific:
            prior_categories = {s.category for s in prior}
            if not (level_categories - prior_categories):
                reasons.append(f"no new level-specific fault domain for {level.name}")

        for scenario in applicable:
            result = by_id.get(scenario.scenario_id)
            if result is None:
                reasons.append(f"missing evidence: {scenario.scenario_id}")
            elif not result.passed:
                reasons.append(f"failed scenario: {scenario.scenario_id}")

        high_severity = [s for s in applicable if s.severity >= 4]
        if level >= OmegaLevel.L4 and not high_severity:
            reasons.append("no high-severity recovery evidence")

        # High-autonomy levels must add high-severity evidence at that level,
        # preventing L4+ from being certified only by inherited lower-level faults.
        if level >= OmegaLevel.L4 and level_specific and not any(s.severity >= 4 for s in level_specific):
            reasons.append(f"no level-specific high-severity evidence for {level.name}")

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
