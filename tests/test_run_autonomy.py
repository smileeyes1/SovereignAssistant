import pytest

from app.hakim.run_autonomy import build_runtime_from_env


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


def test_file_write_mode_fails_closed_without_coding_credentials(tmp_path):
    env = base_env(tmp_path)
    env["OMEGA_ALLOW_FILE_WRITE"] = "true"
    with pytest.raises(ValueError, match="OMEGA_OPENAI_API_KEY"):
        build_runtime_from_env(env)


def test_file_write_mode_installs_ci_repair_when_provider_is_configured(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "OMEGA_ALLOW_FILE_WRITE": "true",
        "OMEGA_OPENAI_API_KEY": "key",
        "OMEGA_OPENAI_MODEL": "model-x",
    })
    runtime = build_runtime_from_env(env, provider_opener=lambda req, timeout: None)
    assert runtime.registry.get("repair-failing-ci").name == "repair-failing-ci"
    assert runtime.github.policy.allow_file_write is True


def test_autonomous_merge_remains_disabled_unless_explicit(tmp_path):
    runtime = build_runtime_from_env(base_env(tmp_path))
    assert runtime.config.allow_merge is False
    assert runtime.github.policy.allow_merge is False
