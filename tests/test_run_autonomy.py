import pytest

from app.hakim.goal_governor import GoalPortfolio
from app.hakim.run_autonomy import ROADMAP_BOOTSTRAP_EVENT, build_runtime_from_env


def base_env(tmp_path):
    return {
        "OMEGA_REPOSITORY": "o/r",
        "OMEGA_GITHUB_TOKEN": "token",
        "OMEGA_GITHUB_WEBHOOK_SECRET": "secret",
        "OMEGA_RUNTIME_TOKEN": "runtime",
        "OMEGA_DB_PATH": str(tmp_path / "omega.db"),
        "OMEGA_PORT": "8080",
    }


def test_bootstrap_installs_concrete_development_actions(tmp_path):
    runtime = build_runtime_from_env(base_env(tmp_path))
    assert runtime.registry.get("merge-verified-pr").name == "merge-verified-pr"
    assert runtime.registry.get("record-ci-failure").name == "record-ci-failure"
    with pytest.raises(KeyError):
        runtime.registry.get("repair-failing-ci")
    assert runtime.state.get_state("omega.cost_policy")["mode"] == "free-only"


def test_file_write_mode_fails_closed_without_local_or_free_provider(tmp_path):
    env = base_env(tmp_path)
    env["OMEGA_ALLOW_FILE_WRITE"] = "true"
    with pytest.raises(ValueError, match="local/free coding provider"):
        build_runtime_from_env(env)


def test_paid_credentials_alone_never_enable_spend(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_OPENAI_API_KEY": "key",
        "OMEGA_OPENAI_MODEL": "model-x",
    })
    with pytest.raises(ValueError, match="paid providers are disabled by default"):
        build_runtime_from_env(env)


def test_file_write_mode_installs_with_local_zero_cost_provider(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_LOCAL_MODEL": "local-model",
        "OMEGA_LOCAL_API_BASE_URL": "http://127.0.0.1:11434/v1",
    })
    runtime = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    assert runtime.registry.get("repair-failing-ci").name == "repair-failing-ci"
    assert runtime.registry.get("advance-goal-portfolio-manual_signal").name == "advance-goal-portfolio-manual_signal"
    assert runtime.registry.get("complete-merged-goal").name == "complete-merged-goal"
    goals = GoalPortfolio(runtime).all()
    assert goals
    assert goals[0].goal_id == "ingress-hardening"
    queued = runtime.queue.get(ROADMAP_BOOTSTRAP_EVENT)
    assert queued is not None
    assert queued.status == "pending"
    assert runtime.github.policy.allow_file_write is True
    usage = runtime.state.get_state("omega.provider_usage")
    assert usage["cost_mode"] == "free-only"
    assert usage["provider_order"] == ["local-openai-compatible"]
    assert usage["paid_call_budget"] == 0


def test_file_write_mode_installs_with_explicit_free_remote_provider(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_FREE_MODEL": "free-model",
        "OMEGA_FREE_API_BASE_URL": "https://free.example/v1",
        "OMEGA_FREE_API_KEY": "free-key",
    })
    runtime = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    usage = runtime.state.get_state("omega.provider_usage")
    assert usage["provider_order"] == ["free-openai-compatible"]
    assert usage["provider_tiers"]["free-openai-compatible"] == "free"


def test_paid_break_glass_requires_explicit_flag_and_finite_budget(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_PAID_PROVIDERS_ALLOWED": "true",
        "OMEGA_PAID_PROVIDER_MAX_CALLS": "1",
        "OMEGA_OPENAI_API_KEY": "key",
        "OMEGA_OPENAI_MODEL": "model-x",
    })
    runtime = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    usage = runtime.state.get_state("omega.provider_usage")
    assert usage["cost_mode"] == "free-first-paid-break-glass"
    assert usage["provider_order"] == ["openai-responses"]
    assert usage["paid_call_budget"] == 1


def test_local_provider_is_always_prioritized_over_paid_break_glass(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_LOCAL_MODEL": "local-model",
        "OMEGA_PAID_PROVIDERS_ALLOWED": "true",
        "OMEGA_PAID_PROVIDER_MAX_CALLS": "1",
        "OMEGA_OPENAI_API_KEY": "key",
        "OMEGA_OPENAI_MODEL": "model-x",
    })
    runtime = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    usage = runtime.state.get_state("omega.provider_usage")
    assert usage["provider_order"] == ["local-openai-compatible", "openai-responses"]


def test_roadmap_seed_and_bootstrap_event_are_idempotent_across_restart(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_LOCAL_MODEL": "local-model",
    })
    first = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    original = [goal.goal_id for goal in GoalPortfolio(first).all()]
    second = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    assert [goal.goal_id for goal in GoalPortfolio(second).all()] == original
    assert second.queue.get(ROADMAP_BOOTSTRAP_EVENT) is not None


def test_autonomous_merge_remains_disabled_unless_explicit(tmp_path):
    runtime = build_runtime_from_env(base_env(tmp_path))
    assert runtime.config.allow_merge is False
    assert runtime.github.policy.allow_merge is False
