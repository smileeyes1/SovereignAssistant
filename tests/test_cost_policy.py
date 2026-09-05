import pytest

from app.hakim.cost_policy import CostPolicy, CostTier


def test_default_policy_is_strictly_free_only():
    policy = CostPolicy()
    assert policy.mode == "free-only"
    assert policy.admits(CostTier.LOCAL)
    assert policy.admits(CostTier.FREE)
    assert policy.admits(CostTier.UNKNOWN)
    assert not policy.admits(CostTier.PAID)


def test_paid_break_glass_requires_explicit_positive_budget():
    disabled_budget = CostPolicy(allow_paid=True, max_paid_calls=0)
    assert not disabled_budget.admits(CostTier.PAID)

    policy = CostPolicy(allow_paid=True, max_paid_calls=2)
    assert policy.mode == "free-first-paid-break-glass"
    assert policy.admits(CostTier.PAID, paid_calls_used=0)
    assert policy.admits(CostTier.PAID, paid_calls_used=1)
    assert not policy.admits(CostTier.PAID, paid_calls_used=2)


def test_policy_from_env_defaults_to_no_paid_spend():
    policy = CostPolicy.from_env({})
    assert policy.allow_paid is False
    assert policy.max_paid_calls == 0
    assert policy.max_failure_log_chars == 8_000
    assert policy.max_output_tokens == 3_072


def test_policy_from_env_rejects_negative_budgets():
    with pytest.raises(ValueError, match="non-negative"):
        CostPolicy.from_env({"OMEGA_PAID_PROVIDER_MAX_CALLS": "-1"})
