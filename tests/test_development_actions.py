import json

from app.hakim.development_actions import AutonomousDevelopmentActions
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.production import ProductionConfig, build_production_runtime


class Response:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode()


def make_runtime(tmp_path, opener, allow_merge=True):
    cfg = ProductionConfig(
        database_path=tmp_path / "omega.db",
        worker_id="w",
        repository="o/r",
        github_token="t",
        github_webhook_secret="s",
        runtime_token="rt",
        host="127.0.0.1",
        port=0,
        allow_merge=allow_merge,
    )
    runtime = build_production_runtime(cfg, github_opener=opener)
    AutonomousDevelopmentActions(runtime).install()
    return runtime


def success_opener(calls):
    def opener(req, timeout):
        calls.append((req.get_method(), req.full_url, None if req.data is None else json.loads(req.data.decode())))
        if req.get_method() == "GET" and "/pulls/8" in req.full_url:
            return Response({"number": 8, "state": "open", "mergeable": True, "head": {"sha": "abc"}})
        if req.get_method() == "GET" and "/actions/runs" in req.full_url:
            return Response({"workflow_runs": [{"id": 1, "status": "completed", "conclusion": "success"}]})
        if req.get_method() == "PUT" and "/pulls/8/merge" in req.full_url:
            return Response({"merged": True, "sha": "merge-sha"})
        raise AssertionError(req.full_url)
    return opener


def ci_event():
    return ContinuationEvent(
        "delivery-1",
        EventType.CI_SUCCEEDED,
        "abc",
        {"workflow_run": {"pull_requests": [{"number": 8}], "head_sha": "abc", "conclusion": "success"}},
    )


def test_verified_ci_can_merge_when_explicitly_enabled(tmp_path):
    calls = []
    runtime = make_runtime(tmp_path, success_opener(calls), allow_merge=True)
    result = runtime.governor.engine().handle(ci_event())
    assert result.status == "executed"
    assert result.selected_action == "merge-verified-pr"
    assert calls[-1][0] == "PUT"
    assert calls[-1][2] == {"sha": "abc", "merge_method": "squash"}
    assert runtime.state.get_state("omega.development.last_merge") == {"pr": 8, "head_sha": "abc", "merge_sha": "merge-sha"}


def test_autonomous_merge_is_blocked_by_default_policy(tmp_path):
    runtime = make_runtime(tmp_path, lambda req, timeout: (_ for _ in ()).throw(AssertionError("network must not be called")), allow_merge=False)
    result = runtime.governor.engine().handle(ci_event())
    assert result.status == "blocked"


def test_merge_rechecks_all_workflows_and_refuses_incomplete_evidence(tmp_path):
    def opener(req, timeout):
        if "/pulls/8" in req.full_url:
            return Response({"number": 8, "state": "open", "mergeable": True, "head": {"sha": "abc"}})
        if "/actions/runs" in req.full_url:
            return Response({"workflow_runs": [{"id": 1, "status": "in_progress", "conclusion": None}]})
        raise AssertionError("merge must not be attempted")
    runtime = make_runtime(tmp_path, opener, allow_merge=True)
    result = runtime.governor.engine().handle(ci_event())
    assert result.status == "failed"
    assert runtime.governor.failure_count("delivery-1", "merge-verified-pr") == 1


def test_ci_failure_is_persisted_for_recovery(tmp_path):
    runtime = make_runtime(tmp_path, lambda req, timeout: Response({}), allow_merge=False)
    event = ContinuationEvent("d2", EventType.CI_FAILED, "bad-sha", {"workflow_run": {"conclusion": "failure"}})
    result = runtime.governor.engine().handle(event)
    assert result.status == "executed"
    saved = runtime.state.get_state("omega.development.last_ci_failure")
    assert saved["subject"] == "bad-sha"
