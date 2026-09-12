"""Adaptive intelligence-fabric router for HAKIM Ω.

The fabric does not pretend that named methods were executed. It produces an
explicit, deterministic routing plan describing which reasoning families should
be activated for a task. Execution evidence remains the responsibility of the
caller and the normal HAKIM verification gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class RiskTier(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(frozen=True)
class IntelligenceFamily:
    name: str
    triggers: frozenset[str]
    methods: tuple[str, ...]
    base_priority: int = 0


@dataclass(frozen=True)
class IntelligenceRequest:
    signals: frozenset[str]
    risk: RiskTier = RiskTier.LOW
    uncertainty: float = 0.0
    requires_execution: bool = False
    persistent: bool = False
    claimed_improvement: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be in [0,1]")


@dataclass(frozen=True)
class IntelligenceSelection:
    family: str
    methods: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]
    mandatory: bool


FAMILIES: tuple[IntelligenceFamily, ...] = (
    IntelligenceFamily("intent_contract", frozenset({"intent", "ambiguity", "constraints", "acceptance", "context"}), ("contract_extraction", "constraint_compilation", "dependency_mapping"), 10),
    IntelligenceFamily("evidence", frozenset({"facts", "freshness", "conflict", "uncertainty", "source"}), ("source_ranking", "triangulation", "counterevidence", "provenance"), 9),
    IntelligenceFamily("logic", frozenset({"rules", "consistency", "deduction", "conditions"}), ("deduction", "invariant_check", "necessary_sufficient_analysis", "contradiction_search"), 5),
    IntelligenceFamily("probabilistic", frozenset({"uncertainty", "forecast", "noisy_data", "risk"}), ("bayesian_update", "probability_model", "calibration", "sensitivity_analysis"), 5),
    IntelligenceFamily("causal_counterfactual", frozenset({"why", "cause", "intervention", "root_cause", "counterfactual", "failure"}), ("causal_graph", "five_whys", "fault_tree", "counterfactual_analysis"), 6),
    IntelligenceFamily("quantitative", frozenset({"numbers", "optimization", "measurement", "tradeoff"}), ("mathematical_model", "constraint_optimization", "pareto_analysis", "calculation"), 5),
    IntelligenceFamily("algorithmic", frozenset({"code", "automation", "search_space", "computation"}), ("decomposition", "graph_search", "dynamic_programming", "branch_and_bound", "simulation"), 5),
    IntelligenceFamily("systems", frozenset({"system", "architecture", "dependencies", "feedback", "bottleneck", "integration"}), ("systems_map", "interface_analysis", "bottleneck_analysis", "resilience_design"), 7),
    IntelligenceFamily("decision_strategy", frozenset({"choice", "strategy", "tradeoff", "irreversibility", "stakeholders"}), ("decision_matrix", "expected_utility", "scenario_planning", "game_theory_when_relevant"), 6),
    IntelligenceFamily("creative", frozenset({"novelty", "stuck", "design", "alternatives", "single_path_failure"}), ("divergent_generation", "analogy", "recombination", "assumption_reversal", "simplification"), 4),
    IntelligenceFamily("adversarial", frozenset({"high_stakes", "security", "failure_modes", "release", "attack_surface"}), ("red_team", "edge_cases", "mutation_testing", "fmea", "differential_testing"), 5),
    IntelligenceFamily("language_semantics", frozenset({"text", "meaning", "ambiguity", "persuasion", "arabic", "user_visible_text"}), ("semantic_analysis", "ambiguity_resolution", "rhetorical_edit", "arabic_quality_gate"), 4),
    IntelligenceFamily("visual_spatial", frozenset({"image", "layout", "pdf", "geometry", "ui", "visual_artifact"}), ("visual_inspection", "geometry_check", "overlap_clip_alignment_check", "user_eye_gate"), 5),
    IntelligenceFamily("human_context", frozenset({"people", "incentives", "emotion", "social", "behavior"}), ("stakeholder_analysis", "incentive_analysis", "perspective_taking", "context_fit"), 4),
    IntelligenceFamily("domain_pedagogy", frozenset({"domain", "education", "curriculum", "specialist"}), ("domain_rules", "official_source_check", "age_fit", "misconception_analysis"), 5),
    IntelligenceFamily("ethics_sharia_rights", frozenset({"ethics", "religion", "rights", "harm", "legality", "safety"}), ("rights_gate", "harm_analysis", "quran_sunnah_verification_when_religious", "valid_disagreement_check"), 8),
    IntelligenceFamily("security_privacy", frozenset({"credentials", "permissions", "remote_control", "sensitive_data", "attack_surface", "security"}), ("threat_model", "least_privilege", "data_minimization", "isolation", "fail_closed"), 8),
    IntelligenceFamily("operational_execution", frozenset({"action", "tool", "workflow", "automation", "artifact", "execution"}), ("action_plan", "tool_routing", "transaction_boundary", "actual_output_verify"), 7),
    IntelligenceFamily("memory_learning", frozenset({"state", "history", "regression", "repeat_failure", "reuse", "persistent"}), ("state_restore", "proven_success_freeze", "known_failure_guard", "rollback", "assetization"), 6),
    IntelligenceFamily("metacognitive", frozenset({"uncertainty", "complexity", "confidence", "method_choice"}), ("confidence_calibration", "unknowns_inventory", "method_selection", "stop_rule"), 9),
    IntelligenceFamily("ensemble", frozenset({"critical", "independent_check", "disagreement", "complexity"}), ("independent_paths", "role_panel", "tmr_when_useful", "evidence_weighted_merge"), 4),
    IntelligenceFamily("temporal_future", frozenset({"time", "deadline", "trend", "sequence", "forecast"}), ("timeline", "dependency_schedule", "trend_analysis", "scenario_horizon"), 4),
    IntelligenceFamily("experimental_measurement", frozenset({"test", "benchmark", "hypothesis", "comparison", "measurement", "improvement"}), ("baseline", "experiment_design", "ab_test_when_relevant", "repeatability_check"), 5),
    IntelligenceFamily("simplicity_economy", frozenset({"cost", "burden", "complexity", "maintenance"}), ("minimum_sufficient_solution", "dependency_reduction", "cost_benefit", "complexity_budget"), 8),
)

_FAMILY_BY_NAME = {family.name: family for family in FAMILIES}
_ALWAYS = {"intent_contract", "metacognitive", "simplicity_economy"}


def _mandatory_names(request: IntelligenceRequest) -> set[str]:
    names = set(_ALWAYS)
    s = request.signals
    if s & {"facts", "freshness", "conflict", "source", "material_factual_claim"}:
        names.add("evidence")
    if s & {"failure", "repair", "root_cause", "single_path_failure"}:
        names.update({"causal_counterfactual", "creative"})
    if s & {"multi_component_change", "integration", "architecture", "system"}:
        names.add("systems")
    if s & {"consequential_choice", "irreversibility"}:
        names.add("decision_strategy")
    if s & {"user_visible_text"}:
        names.add("language_semantics")
    if s & {"visual_artifact", "pdf", "image", "ui"}:
        names.add("visual_spatial")
    if s & {"specialized_domain", "education", "curriculum"}:
        names.add("domain_pedagogy")
    if s & {"rights", "religion", "safety", "harm", "legality"}:
        names.add("ethics_sharia_rights")
    if s & {"security", "sensitive_data", "permissions", "remote_control", "credentials"}:
        names.add("security_privacy")
    if request.requires_execution or s & {"execution", "action", "tool", "workflow", "artifact"}:
        names.add("operational_execution")
    if request.persistent or s & {"persistent", "state", "regression", "reuse"}:
        names.add("memory_learning")
    if request.claimed_improvement or s & {"improvement", "benchmark"}:
        names.add("experimental_measurement")
    if request.risk >= RiskTier.HIGH:
        names.update({"evidence", "adversarial", "decision_strategy", "security_privacy"})
    if request.risk >= RiskTier.CRITICAL:
        names.add("ensemble")
    if request.uncertainty >= 0.60:
        names.update({"evidence", "probabilistic"})
    return names


def select_intelligence(request: IntelligenceRequest) -> tuple[IntelligenceSelection, ...]:
    """Return deterministic, explainable intelligence-family routing.

    Every mandatory guard is returned even with zero trigger overlap. Optional
    families need material signal overlap. A higher score means earlier use;
    callers still must execute and verify the selected methods.
    """
    mandatory = _mandatory_names(request)
    selections: list[IntelligenceSelection] = []
    for family in FAMILIES:
        overlap = sorted(request.signals & family.triggers)
        is_mandatory = family.name in mandatory
        if not overlap and not is_mandatory:
            continue
        score = family.base_priority + len(overlap) * 4
        reasons: list[str] = []
        if overlap:
            reasons.append("signals:" + ",".join(overlap))
        if is_mandatory:
            score += 20
            reasons.append("mandatory_guard")
        if request.risk >= RiskTier.HIGH and family.name in {"evidence", "adversarial", "decision_strategy", "security_privacy", "ensemble"}:
            score += 8 * int(request.risk)
            reasons.append("risk_tier")
        if request.uncertainty >= 0.60 and family.name in {"evidence", "probabilistic", "metacognitive"}:
            score += round(request.uncertainty * 10)
            reasons.append("uncertainty")
        selections.append(IntelligenceSelection(family.name, family.methods, score, tuple(reasons), is_mandatory))
    return tuple(sorted(selections, key=lambda item: (-item.score, item.family)))


def selected_family_names(request: IntelligenceRequest) -> tuple[str, ...]:
    return tuple(item.family for item in select_intelligence(request))


def composition_plan(request: IntelligenceRequest) -> tuple[str, ...]:
    """Build a stable high-level composition sequence for the selected fabric."""
    names = set(selected_family_names(request))
    plan: list[str] = ["intent_contract"]
    for name in ("evidence", "domain_pedagogy", "logic", "probabilistic", "causal_counterfactual", "quantitative", "algorithmic", "systems"):
        if name in names:
            plan.append(name)
    for name in ("creative", "human_context", "temporal_future", "decision_strategy"):
        if name in names:
            plan.append(name)
    if "ensemble" in names:
        plan.append("ensemble")
    for name in ("ethics_sharia_rights", "security_privacy"):
        if name in names:
            plan.append(name)
    if "operational_execution" in names:
        plan.append("operational_execution")
    for name in ("visual_spatial", "language_semantics", "adversarial", "experimental_measurement", "memory_learning"):
        if name in names:
            plan.append(name)
    plan.extend(["metacognitive", "simplicity_economy"])
    # Preserve order while removing duplicates.
    return tuple(dict.fromkeys(plan))


def validate_registry(families: Iterable[IntelligenceFamily] = FAMILIES) -> None:
    items = tuple(families)
    names = [item.name for item in items]
    if len(names) != len(set(names)):
        raise ValueError("duplicate intelligence family")
    if not items:
        raise ValueError("intelligence registry cannot be empty")
    for item in items:
        if not item.name.strip() or not item.methods:
            raise ValueError("every intelligence family needs a name and methods")
        if any(not method.strip() for method in item.methods):
            raise ValueError(f"blank method in {item.name}")


validate_registry()
