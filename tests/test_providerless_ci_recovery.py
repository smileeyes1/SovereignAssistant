from types import SimpleNamespace

import pytest

from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.providerless_ci_recovery import ProviderlessCIRecovery
from app.hakim.recovery_governor import ActionRegistry, RecoveryGovernor


class MemoryState:
    def __init__(self):
        self.values = {"omega.providerless_ci_recovery.enabled": True}

    def get_state(self, key, default=None):
        return self.values.get(key, default)

    def set_state(self, key, value):
        self.values[key] = value


class FakeGitHub:
    repo_path = "/repos/owner/repo"

    def __init__(self, logs):
        self.logs = logs
        self.calls = []

    def workflow_logs(self, run_id, max_chars=100_000):
        self.calls.append(("logs", run_id, max_chars))
        return self.logs

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return {}


def event(run_id=99, conclusion="failure"):
    return ContinuationEvent(
        "delivery-1",
        EventType.CI_FAILED,
        "head-sha",
        {"workflow_run": {"id": run_id, "conclusion": conclusion}},
    )


def runtime(logs):
    state = MemoryState()
    registry = ActionRegistry()
    return SimpleNamespace(state=state, registry=registry, github=FakeGitHub(logs))


def test_transient_ci_rerun_passes_governance_and_mission_then_reruns_once():
    rt = runtime("The runner has received a shutdown signal")
    recovery = ProviderlessCIRecovery(rt)
    recovery.install()
    governor = RecoveryGovernor(rt.registry, rt.state)
    candidates = governor.candidates(event())
    candidate = next(item for item in candidates if item.name == "rerun-transient-ci-failure")
    assert candidate.safe and candidate.authorized and candidate.ready

    governor.execute(candidate, event())

    assert ("POST", "/repos/owner/repo/actions/runs/99/rerun-failed-jobs", None) in rt.github.calls
    assert recovery.attempt_count(99) == 1
    assert rt.state.get_state("omega.providerless_ci_recovery.last")["evidence"] == "the runner has received a shutdown signal"
    assert recovery.ready(event()) is False


def test_code_failure_is_not_rerun_without_explicit_transient_evidence():
    rt = runtime("FAILED tests/test_core.py::test_policy - AssertionError")
    recovery = ProviderlessCIRecovery(rt)
    recovery.install()
    governor = RecoveryGovernor(rt.registry, rt.state)
    candidate = next(item for item in governor.candidates(event()) if item.name == "rerun-transient-ci-failure")
    assert candidate.safe and candidate.authorized
    assert candidate.ready is False
    assert not any(call[0] == "POST" for call in rt.github.calls)
    with pytest.raises(RuntimeError, match="not deterministically classified"):
        recovery.rerun(event())


def test_startup_failure_is_rerunnable_without_model_or_log_heuristics():
    rt = runtime("")
    recovery = ProviderlessCIRecovery(rt)
    recovery.install()
    governor = RecoveryGovernor(rt.registry, rt.state)
    candidate = next(item for item in governor.candidates(event(conclusion="startup_failure")) if item.name == "rerun-transient-ci-failure")
    assert candidate.ready
    governor.execute(candidate, event(conclusion="startup_failure"))
    assert recovery.attempt_count(99) == 1


def test_providerless_recovery_is_fail_closed_when_disabled():
    rt = runtime("HTTP 503 Service Unavailable")
    rt.state.set_state("omega.providerless_ci_recovery.enabled", False)
    recovery = ProviderlessCIRecovery(rt)
    recovery.install()
    governor = RecoveryGovernor(rt.registry, rt.state)
    candidate = next(item for item in governor.candidates(event()) if item.name == "rerun-transient-ci-failure")
    assert candidate.ready is False
    with pytest.raises(PermissionError, match="disabled"):
        recovery.rerun(event())
