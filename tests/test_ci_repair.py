import pytest

from app.hakim.ci_repair import CISelfRepair
from app.hakim.coding_provider import CodingProviderPool, PatchPlan
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.production import ProductionConfig, build_production_runtime


class Provider:
    name = "repairer"
    def __init__(self, changes=None):
        self.changes = changes or {"x.py": "value = 2\n"}
        self.requests = []
    def propose_patch(self, request):
        self.requests.append(request)
        return PatchPlan(self.name, "fix failing assertion", self.changes)


class FakeGitHub:
    def __init__(self):
        self.commits = []
    def pull_requests_for_commit(self, sha):
        return [{"number": 7, "state": "open"}]
    def get_pull_request(self, number):
        return {"number": number, "state": "open", "head": {"sha": "badsha", "ref": "feature/fix", "repo": {"full_name": "o/r"}}}
    def pull_request_files(self, number):
        return [{"filename": "x.py", "status": "modified"}]
    def get_file(self, path, ref):
        return "blob", "value = 1\n"
    def workflow_logs(self, run_id):
        return "FAILED test_x: expected 2"
    def commit_files(self, branch, expected_head_sha, changes, message):
        self.commits.append((branch, expected_head_sha, changes, message))
        return "fixedsha"


def runtime(tmp_path, allow_file_write=True):
    cfg = ProductionConfig(
        database_path=tmp_path / "omega.db", worker_id="w", repository="o/r",
        github_token="t", github_webhook_secret="s", runtime_token="r",
        host="127.0.0.1", port=0, allow_file_write=allow_file_write,
    )
    rt = build_production_runtime(cfg)
    rt.github = FakeGitHub()
    return rt


def event():
    return ContinuationEvent(
        "delivery-fail-1", EventType.CI_FAILED, "badsha",
        {"workflow_run": {"id": 99, "conclusion": "failure", "pull_requests": [{"number": 7}]}},
    )


def test_ci_failure_generates_scoped_patch_and_commits_atomically(tmp_path):
    rt = runtime(tmp_path)
    provider = Provider()
    repair = CISelfRepair(rt, CodingProviderPool([provider]))
    repair.install()
    result = rt.governor.engine().handle(event())
    assert result.status == "executed"
    assert result.selected_action == "repair-failing-ci"
    assert provider.requests[0].failure_log == "FAILED test_x: expected 2"
    assert provider.requests[0].files == {"x.py": "value = 1\n"}
    assert rt.github.commits[0][0:3] == ("feature/fix", "badsha", {"x.py": "value = 2\n"})
    saved = rt.state.get_state("omega.ci_repair.last")
    assert saved["new_sha"] == "fixedsha"
    assert saved["attempt"] == 1


def test_provider_cannot_write_outside_observed_pr_scope(tmp_path):
    rt = runtime(tmp_path)
    repair = CISelfRepair(rt, CodingProviderPool([Provider({"other.py": "x"})]))
    repair.install()
    result = rt.governor.engine().handle(event())
    assert result.status == "failed"
    assert rt.github.commits == []


def test_repair_budget_blocks_endless_self_modification(tmp_path):
    rt = runtime(tmp_path)
    repair = CISelfRepair(rt, CodingProviderPool([Provider()]), max_repairs_per_pr=1)
    repair.install()
    rt.state.set_state("omega.ci_repair.pr.7.attempts", 1)
    result = rt.governor.engine().handle(event())
    assert result.status == "blocked"


def test_file_write_policy_blocks_repair_before_execution(tmp_path):
    rt = runtime(tmp_path, allow_file_write=False)
    repair = CISelfRepair(rt, CodingProviderPool([Provider()]))
    repair.install()
    result = rt.governor.engine().handle(event())
    assert result.status == "blocked"
