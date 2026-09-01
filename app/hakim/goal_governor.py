"""Durable goal portfolio and autonomous development governor for Ω APEX."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from hashlib import sha256
import re
from typing import Iterable
from urllib.parse import quote

from .coding_provider import CodingProviderPool, PatchRequest
from .core import ActionRisk
from .event_continuation import ContinuationEvent, EventType
from .production import ProductionRuntime
from .recovery_governor import RegisteredAction, strong_claim


class GoalStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Goal:
    goal_id: str
    title: str
    objective: str
    priority: float
    dependencies: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    context_paths: tuple[str, ...] = ()
    status: GoalStatus = GoalStatus.PLANNED
    branch: str | None = None
    pr_number: int | None = None
    head_sha: str | None = None
    completion_evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.goal_id.strip() or not self.title.strip() or not self.objective.strip():
            raise ValueError("goal_id, title and objective are required")
        if self.goal_id in self.dependencies:
            raise ValueError("goal cannot depend on itself")


class GoalPortfolio:
    KEY = "omega.goal_portfolio.v1"

    def __init__(self, runtime: ProductionRuntime):
        self.runtime = runtime

    @staticmethod
    def _encode(goal: Goal) -> dict[str, object]:
        value = asdict(goal)
        value["status"] = goal.status.value
        value["dependencies"] = list(goal.dependencies)
        value["acceptance"] = list(goal.acceptance)
        value["context_paths"] = list(goal.context_paths)
        return value

    @staticmethod
    def _decode(value: dict[str, object]) -> Goal:
        return Goal(
            goal_id=str(value["goal_id"]),
            title=str(value["title"]),
            objective=str(value["objective"]),
            priority=float(value["priority"]),
            dependencies=tuple(str(x) for x in value.get("dependencies", [])),
            acceptance=tuple(str(x) for x in value.get("acceptance", [])),
            context_paths=tuple(str(x) for x in value.get("context_paths", [])),
            status=GoalStatus(str(value.get("status", GoalStatus.PLANNED.value))),
            branch=None if value.get("branch") is None else str(value["branch"]),
            pr_number=None if value.get("pr_number") is None else int(value["pr_number"]),
            head_sha=None if value.get("head_sha") is None else str(value["head_sha"]),
            completion_evidence=None if value.get("completion_evidence") is None else str(value["completion_evidence"]),
        )

    def all(self) -> list[Goal]:
        raw = self.runtime.state.get_state(self.KEY, [])
        return [self._decode(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def save_all(self, goals: Iterable[Goal]) -> None:
        items = list(goals)
        ids = [g.goal_id for g in items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate goal_id")
        known = set(ids)
        missing = sorted({dep for goal in items for dep in goal.dependencies if dep not in known})
        if missing:
            raise ValueError("unknown goal dependencies: " + ", ".join(missing))
        self.runtime.state.set_state(self.KEY, [self._encode(g) for g in items])

    def seed_if_empty(self, goals: Iterable[Goal]) -> bool:
        if self.all():
            return False
        self.save_all(goals)
        return True

    def get(self, goal_id: str) -> Goal:
        for goal in self.all():
            if goal.goal_id == goal_id:
                return goal
        raise KeyError(goal_id)

    def update(self, goal: Goal) -> None:
        goals = self.all()
        updated = False
        for index, current in enumerate(goals):
            if current.goal_id == goal.goal_id:
                goals[index] = goal
                updated = True
                break
        if not updated:
            raise KeyError(goal.goal_id)
        self.save_all(goals)

    def next_ready(self) -> Goal | None:
        goals = self.all()
        completed = {g.goal_id for g in goals if g.status == GoalStatus.COMPLETED}
        ready = [
            g for g in goals
            if g.status == GoalStatus.PLANNED and all(dep in completed for dep in g.dependencies)
        ]
        return sorted(ready, key=lambda g: (-g.priority, g.goal_id))[0] if ready else None

    def active(self) -> list[Goal]:
        return [g for g in self.all() if g.status in {GoalStatus.IN_PROGRESS, GoalStatus.VERIFYING}]

    def by_pr(self, pr_number: int) -> Goal | None:
        return next((g for g in self.all() if g.pr_number == pr_number), None)


class GoalGitHubBridge:
    """Development-only GitHub operations over the owned GitHubControl transport."""

    def __init__(self, runtime: ProductionRuntime):
        self.runtime = runtime
        self.control = runtime.github

    def branch_head(self, branch: str) -> str:
        result = self.control._request("GET", f"{self.control.repo_path}/git/ref/heads/{quote(branch, safe='')}")
        obj = result.get("object", {}) if isinstance(result, dict) else {}
        sha = str(obj.get("sha", "")) if isinstance(obj, dict) else ""
        if not sha:
            raise RuntimeError(f"branch head missing: {branch}")
        return sha

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> dict[str, object]:
        result = self.control._request(
            "POST", f"{self.control.repo_path}/pulls",
            {"title": title, "body": body, "head": head, "base": base, "draft": False},
        )
        if not isinstance(result, dict) or result.get("number") is None:
            raise RuntimeError("pull request creation was not confirmed")
        return dict(result)


@dataclass
class AutonomousGoalGovernor:
    runtime: ProductionRuntime
    providers: CodingProviderPool
    portfolio: GoalPortfolio
    base_branch: str = "main"
    max_context_files: int = 16

    def install(self) -> None:
        for event_type in (EventType.PR_MERGED, EventType.TASK_COMPLETED, EventType.MANUAL_SIGNAL):
            self.runtime.registry.register(
                RegisteredAction(
                    name=f"advance-goal-portfolio-{event_type.value}",
                    event_types=(event_type,),
                    value=80,
                    risk=ActionRisk.MODERATE,
                    reversible=True,
                    requires_human_approval=False,
                    claim_factory=lambda event: strong_claim("continuation trigger observed", "event-log"),
                    executor=self.advance,
                    ready=lambda event: self.runtime.config.allow_branch_create and self.runtime.config.allow_file_write,
                )
            )
        self.runtime.registry.register(
            RegisteredAction(
                name="complete-merged-goal",
                event_types=(EventType.PR_MERGED,),
                value=120,
                risk=ActionRisk.LOW,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("merged pull request observed", "github-webhook"),
                executor=self.complete_merged_goal,
            )
        )

    @staticmethod
    def _branch_name(goal: Goal, base_sha: str) -> str:
        slug = re.sub(r"[^a-z0-9-]+", "-", goal.goal_id.lower()).strip("-") or "goal"
        digest = sha256(f"{goal.goal_id}\0{base_sha}".encode()).hexdigest()[:10]
        return f"omega/goal-{slug[:40]}-{digest}"

    def _context(self, goal: Goal, ref: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for path in goal.context_paths[: self.max_context_files]:
            try:
                _, content = self.runtime.github.get_file(path, ref)
            except Exception:
                continue
            files[path] = content
        return files

    def advance(self, event: ContinuationEvent) -> None:
        if self.portfolio.active():
            return
        goal = self.portfolio.next_ready()
        if goal is None:
            self.runtime.state.set_state("omega.goals.last_advance", {"status": "idle", "event": event.event_id})
            return
        bridge = GoalGitHubBridge(self.runtime)
        base_sha = bridge.branch_head(self.base_branch)
        context = self._context(goal, base_sha)
        acceptance = "\n".join(f"- {item}" for item in goal.acceptance) or "- objective is implemented without regression"
        plan = self.providers.propose_patch(
            PatchRequest(
                objective=f"{goal.objective}\nAcceptance criteria:\n{acceptance}",
                failure_log="",
                files=context,
            )
        )
        branch = self._branch_name(goal, base_sha)
        self.runtime.github.create_branch(branch, base_sha)
        new_sha = self.runtime.github.commit_files(
            branch,
            base_sha,
            plan.changes,
            f"feat: autonomous goal {goal.goal_id}",
        )
        pr = bridge.create_pull_request(
            goal.title,
            "Autonomously generated by Ω APEX goal governor.\n\nAcceptance:\n" + acceptance,
            branch,
            self.base_branch,
        )
        updated = replace(
            goal,
            status=GoalStatus.VERIFYING,
            branch=branch,
            pr_number=int(pr["number"]),
            head_sha=new_sha,
        )
        self.portfolio.update(updated)
        self.runtime.state.set_state(
            "omega.goals.last_advance",
            {"goal_id": goal.goal_id, "branch": branch, "pr": int(pr["number"]), "head_sha": new_sha, "provider": plan.provider},
        )

    def complete_merged_goal(self, event: ContinuationEvent) -> None:
        payload_pr = event.payload.get("pull_request", {})
        number = None
        if isinstance(payload_pr, dict) and payload_pr.get("number") is not None:
            number = int(payload_pr["number"])
        elif str(event.subject).isdigit():
            number = int(event.subject)
        if number is None:
            raise RuntimeError("merged PR number missing")
        goal = self.portfolio.by_pr(number)
        if goal is None:
            return
        updated = replace(
            goal,
            status=GoalStatus.COMPLETED,
            completion_evidence=f"PR #{number} merged",
        )
        self.portfolio.update(updated)
        self.runtime.state.set_state("omega.goals.last_completed", {"goal_id": goal.goal_id, "pr": number})
