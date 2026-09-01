from app.hakim.coding_provider import CodingProviderPool, PatchPlan
from app.hakim.event_continuation import ContinuationEvent, EventType
from app.hakim.goal_governor import Goal, GoalPortfolio, GoalStatus
from app.hakim.goal_loop import ClosedLoopGoalGovernor
from app.hakim.production import ProductionConfig, build_production_runtime


class Provider:
    name = "builder"
    def __init__(self):
        self.requests = []
    def propose_patch(self, request):
        self.requests.append(request)
        return PatchPlan(self.name, "implement goal", {"app/new.py": "VALUE = 1\n"})


class FakeGitHub:
    def __init__(self):
        self.branches = []
        self.commits = []
        self.prs = []
        self.next_pr = 20
        self.repo_path = "/repos/o/r"
    def _request(self, method, path, payload=None):
        if method == "GET" and "/git/ref/heads/main" in path:
            return {"object": {"sha": "mainsha"}}
        if method == "POST" and path.endswith("/pulls"):
            number = self.next_pr
            self.next_pr += 1
            self.prs.append((number, payload))
            return {"number": number}
        raise AssertionError((method, path, payload))
    def get_file(self, path, ref):
        return "blob", "existing = True\n"
    def create_branch(self, branch, base_sha):
        self.branches.append((branch, base_sha))
        return {"ref": branch}
    def commit_files(self, branch, expected_head_sha, changes, message):
        self.commits.append((branch, expected_head_sha, changes, message))
        return f"commit-{len(self.commits)}"
    def get_pull_request(self, number):
        return {"number": number, "merged": True, "head": {"sha": "old"}}
    def workflow_runs_for_commit(self, sha):
        return [{"status": "completed", "conclusion": "success"}]


def runtime(tmp_path):
    cfg = ProductionConfig(
        database_path=tmp_path / "omega.db",
        worker_id="w",
        repository="o/r",
        github_token="t",
        github_webhook_secret="s",
        runtime_token="r",
        host="127.0.0.1",
        port=0,
        allow_branch_create=True,
        allow_file_write=True,
    )
    rt = build_production_runtime(cfg)
    rt.github = FakeGitHub()
    return rt


def test_portfolio_selects_highest_priority_ready_dependency(tmp_path):
    rt = runtime(tmp_path)
    portfolio = GoalPortfolio(rt)
    portfolio.save_all([
        Goal("a", "A", "first", 10),
        Goal("b", "B", "blocked by a", 100, dependencies=("a",)),
        Goal("c", "C", "independent", 20),
    ])
    assert portfolio.next_ready().goal_id == "c"
    portfolio.update(Goal("c", "C", "independent", 20, status=GoalStatus.COMPLETED))
    assert portfolio.next_ready().goal_id == "a"


def test_goal_advance_creates_branch_atomic_commit_and_pr(tmp_path):
    rt = runtime(tmp_path)
    portfolio = GoalPortfolio(rt)
    portfolio.save_all([
        Goal("g1", "Goal One", "Add capability", 10, acceptance=("tests cover it",), context_paths=("app/hakim/core.py",)),
    ])
    provider = Provider()
    governor = ClosedLoopGoalGovernor(rt, CodingProviderPool([provider]), portfolio)
    governor.install()
    event = ContinuationEvent("manual-1", EventType.MANUAL_SIGNAL, "roadmap")
    result = rt.governor.engine().handle(event)
    assert result.status == "executed"
    goal = portfolio.get("g1")
    assert goal.status == GoalStatus.VERIFYING
    assert goal.pr_number == 20
    assert goal.head_sha == "commit-1"
    assert rt.github.branches[0][1] == "mainsha"
    assert rt.github.commits[0][2] == {"app/new.py": "VALUE = 1\n"}
    assert provider.requests[0].files == {"app/hakim/core.py": "existing = True\n"}


def test_merge_completion_immediately_starts_next_dependent_goal(tmp_path):
    rt = runtime(tmp_path)
    portfolio = GoalPortfolio(rt)
    portfolio.save_all([
        Goal("g1", "Goal One", "first", 20, acceptance=("verified by CI",), status=GoalStatus.VERIFYING, branch="omega/g1", pr_number=7, head_sha="old"),
        Goal("g2", "Goal Two", "second", 10, dependencies=("g1",)),
    ])
    governor = ClosedLoopGoalGovernor(rt, CodingProviderPool([Provider()]), portfolio)
    governor.install()
    event = ContinuationEvent("merge-7", EventType.PR_MERGED, "7", {"pull_request": {"number": 7, "merged": True}})
    result = rt.governor.engine().handle(event)
    assert result.status == "executed"
    assert result.selected_action == "complete-merged-goal"
    assert portfolio.get("g1").status == GoalStatus.COMPLETED
    assert portfolio.get("g2").status == GoalStatus.VERIFYING
    assert portfolio.get("g2").pr_number == 20
    evidence = rt.state.get_state("omega.completion_audit.v1.g1")
    assert evidence["accepted"] is True
    assert evidence["workflow_count"] == 1


def test_completion_audit_rejects_missing_workflow_evidence(tmp_path):
    rt = runtime(tmp_path)
    rt.github.workflow_runs_for_commit = lambda sha: []
    portfolio = GoalPortfolio(rt)
    portfolio.save_all([
        Goal("g1", "Goal One", "first", 20, acceptance=("verified by CI",), status=GoalStatus.VERIFYING, pr_number=7, head_sha="old"),
        Goal("g2", "Goal Two", "second", 10, dependencies=("g1",)),
    ])
    governor = ClosedLoopGoalGovernor(rt, CodingProviderPool([Provider()]), portfolio)
    governor.install()
    event = ContinuationEvent("merge-7", EventType.PR_MERGED, "7", {"pull_request": {"number": 7, "merged": True}})
    result = rt.governor.engine().handle(event)
    assert result.status == "executed"
    assert portfolio.get("g1").status == GoalStatus.VERIFYING
    assert portfolio.get("g2").status == GoalStatus.PLANNED
    evidence = rt.state.get_state("omega.completion_audit.v1.g1")
    assert evidence["accepted"] is False
    assert "no workflow evidence found for merged goal head" in evidence["reasons"]


def test_active_goal_prevents_parallel_uncontrolled_goal_creation(tmp_path):
    rt = runtime(tmp_path)
    portfolio = GoalPortfolio(rt)
    portfolio.save_all([
        Goal("g1", "One", "active", 10, status=GoalStatus.VERIFYING, pr_number=5),
        Goal("g2", "Two", "planned", 100),
    ])
    governor = ClosedLoopGoalGovernor(rt, CodingProviderPool([Provider()]), portfolio)
    governor.advance(ContinuationEvent("x", EventType.MANUAL_SIGNAL, "roadmap"))
    assert rt.github.branches == []
    assert portfolio.get("g2").status == GoalStatus.PLANNED


def test_goal_store_survives_runtime_restart(tmp_path):
    db = tmp_path / "omega.db"
    rt1 = runtime(tmp_path)
    portfolio1 = GoalPortfolio(rt1)
    portfolio1.save_all([Goal("persist", "Persist", "survive restart", 1)])
    cfg = ProductionConfig(
        database_path=db, worker_id="w2", repository="o/r", github_token="t",
        github_webhook_secret="s", runtime_token="r", host="127.0.0.1", port=0,
    )
    rt2 = build_production_runtime(cfg)
    assert GoalPortfolio(rt2).get("persist").objective == "survive restart"
