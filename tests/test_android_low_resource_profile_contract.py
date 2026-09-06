from pathlib import Path


SCRIPT = Path("scripts/install-android-low-resource-profile.sh")


def test_low_resource_profile_is_non_persistent_and_loopback_only():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"persistent_model": False' in text
    assert '"background_daemon_required": False' in text
    assert '"agent_planning_with_local_model": False' in text
    assert '--host 127.0.0.1' in text
    assert '--parallel 1' in text
    assert '--threads 2' in text
    assert '--threads-batch 2' in text
    assert '--reasoning off' in text
    assert '--api-key "$KEY"' in text
    assert "trap 'kill \"$PID\"" in text


def test_low_resource_profile_does_not_create_a_model_daemon():
    text = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "tmux new-session",
        "hakim-model",
        "termux-job-scheduler",
        "daemon start",
        "--persist-session",
    )
    for marker in forbidden:
        assert marker not in text


def test_on_demand_helper_has_bounded_context_and_output():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '-c 1024' in text
    assert '"max_tokens":192' in text
    assert 'MODEL_START_FAILED' in text
    assert 'MODEL_NOT_INSTALLED' in text
