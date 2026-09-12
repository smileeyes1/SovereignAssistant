"""Evidence-aware multi-criteria route optimizer for HAKIM Ω.

This module turns "best" from a slogan into an auditable ranking. It compares
candidate routes across value, fit, evidence, expected success, safety,
burden, cost, dependency, independence, sustainability, speed and
reversibility. Missing evidence is treated neutrally, never as proof of quality.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class RouteProfile:
    method: str = "unspecified"
    style: str = "unspecified"
    medium: str = "unspecified"
    technique: str = "unspecified"
    mechanism: str = "unspecified"
    timing: str = "unspecified"
    fit: float = 0.5
    evidence: float = 0.5
    expected_success: float = 0.5
    safety_margin: float = 0.5
    burden: float = 0.5
    monetary_cost: float = 0.5
    external_dependency: float = 0.5
    independence: float = 0.5
    sustainability: float = 0.5
    speed: float = 0.5

    def __post_init__(self) -> None:
        for name in (
            "fit", "evidence", "expected_success", "safety_margin", "burden",
            "monetary_cost", "external_dependency", "independence",
            "sustainability", "speed",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0,1]")


@dataclass(frozen=True)
class RouteInput:
    name: str
    base_value: float
    risk: int
    reversible: bool
    requires_human_approval: bool
    failure_count: int = 0
    profile: RouteProfile = RouteProfile()


@dataclass(frozen=True)
class RouteAssessment:
    name: str
    score: float
    dominated: bool
    components: dict[str, float]
    route: dict[str, object]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RouteOptimizationContext:
    uncertainty: float = 0.0
    zero_paid_cost: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be in [0,1]")


def _normalize_values(items: tuple[RouteInput, ...]) -> dict[str, float]:
    values = [item.base_value for item in items]
    low, high = min(values), max(values)
    if high == low:
        return {item.name: 0.5 for item in items}
    span = high - low
    return {item.name: (item.base_value - low) / span for item in items}


def _desirability(route: RouteInput) -> tuple[float, ...]:
    p = route.profile
    return (
        p.fit,
        p.evidence,
        p.expected_success,
        p.safety_margin,
        1.0 - p.burden,
        1.0 - p.monetary_cost,
        1.0 - p.external_dependency,
        p.independence,
        p.sustainability,
        p.speed,
        1.0 if route.reversible else 0.0,
        1.0 / (1.0 + route.failure_count),
        1.0 - min(max(route.risk, 0), 3) / 3.0,
    )


def _is_dominated(target: RouteInput, items: tuple[RouteInput, ...]) -> bool:
    t = _desirability(target)
    for other in items:
        if other.name == target.name:
            continue
        o = _desirability(other)
        if all(a >= b for a, b in zip(o, t)) and any(a > b for a, b in zip(o, t)):
            return True
    return False


def optimize_routes(
    routes: Iterable[RouteInput],
    context: RouteOptimizationContext = RouteOptimizationContext(),
) -> tuple[RouteAssessment, ...]:
    items = tuple(routes)
    if not items:
        return ()
    if len({item.name for item in items}) != len(items):
        raise ValueError("route names must be unique")

    normalized_value = _normalize_values(items)
    assessments: list[RouteAssessment] = []
    for item in items:
        p = item.profile
        risk_factor = min(max(item.risk, 0), 3) / 3.0
        uncertainty = context.uncertainty

        # Base weights favor outcome value and contextual fit. High risk raises
        # safety/evidence/reversibility weight; high uncertainty raises evidence.
        weights = {
            "value": 0.20,
            "fit": 0.14,
            "evidence": 0.12 + 0.08 * uncertainty + 0.05 * risk_factor,
            "success": 0.13,
            "safety": 0.10 + 0.10 * risk_factor,
            "low_burden": 0.07,
            "low_cost": 0.06,
            "low_dependency": 0.05,
            "independence": 0.04,
            "sustainability": 0.05,
            "speed": max(0.01, 0.04 - 0.02 * risk_factor),
            "reversibility": 0.04 + 0.08 * risk_factor,
            "failure_resilience": 0.05,
        }
        components = {
            "value": normalized_value[item.name],
            "fit": p.fit,
            "evidence": p.evidence,
            "success": p.expected_success,
            "safety": p.safety_margin,
            "low_burden": 1.0 - p.burden,
            "low_cost": 1.0 - p.monetary_cost,
            "low_dependency": 1.0 - p.external_dependency,
            "independence": p.independence,
            "sustainability": p.sustainability,
            "speed": p.speed,
            "reversibility": 1.0 if item.reversible else 0.0,
            "failure_resilience": 1.0 / (1.0 + item.failure_count),
        }
        total_weight = sum(weights.values())
        score = 100.0 * sum(weights[k] * components[k] for k in weights) / total_weight

        reasons: list[str] = []
        dominated = _is_dominated(item, items)
        if dominated:
            score -= 20.0
            reasons.append("pareto_dominated")
        if item.requires_human_approval:
            score -= 3.0
            reasons.append("human_approval_required")
        if item.failure_count:
            reasons.append(f"prior_failures:{item.failure_count}")
        if context.zero_paid_cost and p.monetary_cost > 0.0:
            score -= 35.0 * p.monetary_cost
            reasons.append("paid_cost_penalty")
        if risk_factor >= 2 / 3:
            reasons.append("high_risk_weights")
        if uncertainty >= 0.60:
            reasons.append("high_uncertainty_weights")

        route = asdict(p)
        assessments.append(
            RouteAssessment(
                name=item.name,
                score=round(score, 6),
                dominated=dominated,
                components={k: round(v, 6) for k, v in components.items()},
                route=route,
                reasons=tuple(reasons),
            )
        )

    return tuple(sorted(assessments, key=lambda item: (-item.score, item.name)))
