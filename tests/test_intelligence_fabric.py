from app.hakim.intelligence_fabric import (
    FAMILIES,
    IntelligenceRequest,
    RiskTier,
    composition_plan,
    selected_family_names,
)


def names(**kwargs):
    return set(selected_family_names(IntelligenceRequest(**kwargs)))


def test_registry_is_broad_unique_and_extensible():
    family_names = [family.name for family in FAMILIES]
    assert len(family_names) >= 24
    assert len(family_names) == len(set(family_names))
    assert all(family.methods for family in FAMILIES)


def test_every_task_gets_governing_baseline_without_method_spam():
    selected = names(signals=frozenset())
    assert {"intent_contract", "metacognitive", "simplicity_economy"} <= selected
    assert "creative" not in selected
    assert "algorithmic" not in selected


def test_high_risk_forces_truth_adversarial_decision_and_security_guards():
    selected = names(signals=frozenset({"choice"}), risk=RiskTier.HIGH)
    assert {"evidence", "adversarial", "decision_strategy", "security_privacy"} <= selected


def test_critical_risk_adds_independent_ensemble_path():
    selected = names(signals=frozenset({"critical"}), risk=RiskTier.CRITICAL)
    assert "ensemble" in selected
    assert "adversarial" in selected


def test_uncertainty_forces_probabilistic_and_evidence_modes():
    selected = names(signals=frozenset({"forecast"}), uncertainty=0.8)
    assert {"evidence", "probabilistic", "metacognitive"} <= selected


def test_failure_forces_root_cause_and_divergent_alternatives():
    selected = names(signals=frozenset({"failure"}))
    assert {"causal_counterfactual", "creative"} <= selected


def test_execution_persistence_and_claimed_improvement_activate_required_modes():
    selected = names(
        signals=frozenset({"automation"}),
        requires_execution=True,
        persistent=True,
        claimed_improvement=True,
    )
    assert {"operational_execution", "memory_learning", "experimental_measurement"} <= selected


def test_visual_education_routes_visual_and_domain_intelligence():
    selected = names(signals=frozenset({"pdf", "education", "curriculum", "user_visible_text"}))
    assert {"visual_spatial", "domain_pedagogy", "language_semantics"} <= selected


def test_security_signals_cannot_route_without_security_guard():
    selected = names(signals=frozenset({"credentials", "permissions", "remote_control"}))
    assert "security_privacy" in selected


def test_composition_is_ordered_deduplicated_and_finishes_with_meta_economy():
    request = IntelligenceRequest(
        signals=frozenset({"facts", "failure", "system", "choice", "automation", "benchmark"}),
        risk=RiskTier.HIGH,
        uncertainty=0.75,
        requires_execution=True,
        persistent=True,
        claimed_improvement=True,
    )
    plan = composition_plan(request)
    assert plan[0] == "intent_contract"
    assert plan[-2:] == ("metacognitive", "simplicity_economy")
    assert len(plan) == len(set(plan))
    assert plan.index("evidence") < plan.index("decision_strategy")
    assert plan.index("decision_strategy") < plan.index("operational_execution")
    assert plan.index("operational_execution") < plan.index("adversarial")
