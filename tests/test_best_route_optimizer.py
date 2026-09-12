from app.hakim.best_route_optimizer import (
    RouteInput,
    RouteOptimizationContext,
    RouteProfile,
    optimize_routes,
)


def profile(**overrides):
    base = dict(
        method="m",
        style="s",
        medium="x",
        technique="t",
        mechanism="k",
        timing="now",
        fit=0.5,
        evidence=0.5,
        expected_success=0.5,
        safety_margin=0.5,
        burden=0.5,
        monetary_cost=0.5,
        external_dependency=0.5,
        independence=0.5,
        sustainability=0.5,
        speed=0.5,
    )
    base.update(overrides)
    return RouteProfile(**base)


def test_lower_raw_value_can_win_when_route_quality_is_materially_better():
    flashy = RouteInput(
        "flashy",
        base_value=100,
        risk=2,
        reversible=True,
        requires_human_approval=False,
        profile=profile(
            fit=0.2,
            evidence=0.1,
            expected_success=0.2,
            safety_margin=0.2,
            burden=0.9,
            monetary_cost=0.8,
            external_dependency=0.9,
            independence=0.1,
            sustainability=0.2,
            speed=0.8,
        ),
    )
    proven = RouteInput(
        "proven",
        base_value=60,
        risk=0,
        reversible=True,
        requires_human_approval=False,
        profile=profile(
            fit=0.95,
            evidence=0.98,
            expected_success=0.95,
            safety_margin=0.98,
            burden=0.1,
            monetary_cost=0.0,
            external_dependency=0.1,
            independence=0.9,
            sustainability=0.95,
            speed=0.75,
        ),
    )

    ranked = optimize_routes((flashy, proven), RouteOptimizationContext(uncertainty=0.7))

    assert ranked[0].name == "proven"
    assert ranked[0].score > ranked[1].score


def test_zero_paid_cost_penalizes_paid_route_without_faking_a_hard_safety_gate():
    paid = RouteInput(
        "paid",
        base_value=90,
        risk=0,
        reversible=True,
        requires_human_approval=False,
        profile=profile(monetary_cost=1.0, fit=0.9, evidence=0.9, expected_success=0.9),
    )
    free = RouteInput(
        "free",
        base_value=80,
        risk=0,
        reversible=True,
        requires_human_approval=False,
        profile=profile(monetary_cost=0.0, fit=0.85, evidence=0.85, expected_success=0.85),
    )

    ranked = optimize_routes((paid, free), RouteOptimizationContext(zero_paid_cost=True))

    assert ranked[0].name == "free"
    paid_assessment = next(item for item in ranked if item.name == "paid")
    assert "paid_cost_penalty" in paid_assessment.reasons


def test_prior_failures_reduce_route_quality_and_are_auditable():
    clean = RouteInput("clean", 10, 0, True, False, failure_count=0, profile=profile())
    failing = RouteInput("failing", 10, 0, True, False, failure_count=3, profile=profile())

    ranked = optimize_routes((clean, failing))

    assert ranked[0].name == "clean"
    failed = next(item for item in ranked if item.name == "failing")
    assert "prior_failures:3" in failed.reasons


def test_pareto_dominated_route_is_explicitly_marked():
    weak = RouteInput(
        "weak",
        10,
        1,
        True,
        False,
        profile=profile(
            fit=0.2,
            evidence=0.2,
            expected_success=0.2,
            safety_margin=0.2,
            burden=0.8,
            monetary_cost=0.8,
            external_dependency=0.8,
            independence=0.2,
            sustainability=0.2,
            speed=0.2,
        ),
    )
    strong = RouteInput(
        "strong",
        10,
        0,
        True,
        False,
        profile=profile(
            fit=0.9,
            evidence=0.9,
            expected_success=0.9,
            safety_margin=0.9,
            burden=0.1,
            monetary_cost=0.1,
            external_dependency=0.1,
            independence=0.9,
            sustainability=0.9,
            speed=0.9,
        ),
    )

    ranked = optimize_routes((weak, strong))

    weak_assessment = next(item for item in ranked if item.name == "weak")
    assert weak_assessment.dominated is True
    assert "pareto_dominated" in weak_assessment.reasons


def test_route_profile_rejects_fake_out_of_range_quality():
    try:
        RouteProfile(evidence=1.1)
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("expected invalid route profile to fail closed")
