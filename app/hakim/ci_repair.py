"""Governed CI-failure repair pipeline for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .coding_provider import CodingProviderPool, PatchRequest
from .core import ActionRisk
from .event_continuation import ContinuationEvent, EventType
from .production import ProductionRuntime
from .recovery_governor import RegisteredAction, strong_claim


@dataclass
class CISelfRepair:
    runtime: ProductionRuntime
    providers: CodingProviderPool
    max_context_files: int = 12
    max_repairs_per_pr: int = 3

    def install(self) -> None:
        self.runtime.registry.register(
            RegisteredAction(
                name="repair-failing-ci",
                event_types=(EventType.CI_FAILED,),
                value=100,
                risk=ActionRisk.MODERATE,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("GitHub reported a concrete CI failure", "github-webhook"),
                executor=self.repair,
                ready=self.ready,
            )
        )

    def _workflow_run(self, event: ContinuationEvent) -> dict[str, object]:
        value = event.payload.get("workflow_run", {})
        if not isinstance(value, dict):
            raise RuntimeError("workflow_run payload missing")
        return value

    def _pr_number(self, event: ContinuationEvent) -> int:
        run = self._workflow_run(event)
        prs = run.get("pull_requests", [])
        if isinstance(prs, list):
            for item in prs:
                if isinstance(item, dict) and item.get("number") is not None:
                    return int(item["number"])
        discovered = self.runtime.github.pull_requests_for_commit(event.subject)
        open_prs = [p for p in discovered if str(p.get("state", "open")) == "open"]
        if len(open_prs) != 1:
            raise RuntimeError(f"expected exactly one open PR, found {len(open_prs)}")
        return int(open_prs[0]["number"])

    def _attempt_key(self, pr_number: int) -> str:
        return f"omega.ci_repair.pr.{pr_number}.attempts"

    def attempt_count(self, pr_number: int) -> int:
        return int(self.runtime.state.get_state(self._attempt_key(pr_number), 0))

    def ready(self, event: ContinuationEvent) -> bool:
        if not self.runtime.config.allow_file_write:
            return False
        try:
            pr_number = self._pr_number(event)
        except Exception:
            return True  # executor records a diagnosable failure; recovery can retry/discover later.
        return self.attempt_count(pr_number) < self.max_repairs_per_pr

    @staticmethod
    def _is_safe_context_path(path: str) -> bool:
        p = PurePosixPath(path)
        return bool(path.strip()) and not p.is_absolute() and ".." not in p.parts and not path.startswith(".")

    def repair(self, event: ContinuationEvent) -> None:
        if not self.runtime.config.allow_file_write:
            raise PermissionError("autonomous file repair is disabled")
        run = self._workflow_run(event)
        run_id = run.get("id")
        if run_id is None:
            raise RuntimeError("workflow run id missing")
        pr_number = self._pr_number(event)
        if self.attempt_count(pr_number) >= self.max_repairs_per_pr:
            raise RuntimeError("autonomous repair budget exhausted for PR")

        pr = self.runtime.github.get_pull_request(pr_number)
        head = pr.get("head", {})
        if not isinstance(head, dict):
            raise RuntimeError("PR head missing")
        head_sha = str(head.get("sha", ""))
        branch = str(head.get("ref", ""))
        head_repo = head.get("repo", {})
        repo_name = str(head_repo.get("full_name", "")) if isinstance(head_repo, dict) else ""
        if not head_sha or head_sha != event.subject:
            raise RuntimeError("PR head does not match failing workflow head")
        if not branch:
            raise RuntimeError("PR branch missing")
        if repo_name and repo_name != self.runtime.config.repository:
            raise RuntimeError("fork PR repair is not allowed by this adapter")

        file_rows = self.runtime.github.pull_request_files(pr_number)
        paths: list[str] = []
        for row in file_rows:
            path = str(row.get("filename", ""))
            if row.get("status") == "removed" or not self._is_safe_context_path(path):
                continue
            paths.append(path)
            if len(paths) >= self.max_context_files:
                break
        if not paths:
            raise RuntimeError("no safe changed files available for repair context")

        files: dict[str, str] = {}
        for path in paths:
            try:
                _, content = self.runtime.github.get_file(path, head_sha)
            except Exception:
                continue
            files[path] = content
        if not files:
            raise RuntimeError("no readable text files available for repair context")

        failure_log = self.runtime.github.workflow_logs(int(run_id))
        plan = self.providers.propose_patch(
            PatchRequest(
                objective=f"Repair failing CI for PR #{pr_number} without regressing working behavior.",
                failure_log=failure_log,
                files=files,
            )
        )
        outside_scope = sorted(set(plan.changes) - set(files))
        if outside_scope:
            raise RuntimeError("provider attempted out-of-scope changes: " + ", ".join(outside_scope))

        new_sha = self.runtime.github.commit_files(
            branch,
            head_sha,
            plan.changes,
            f"fix: autonomous CI repair ({plan.provider})",
        )
        attempts = self.attempt_count(pr_number) + 1
        self.runtime.state.set_state(self._attempt_key(pr_number), attempts)
        self.runtime.state.set_state(
            "omega.ci_repair.last",
            {
                "pr": pr_number,
                "old_sha": head_sha,
                "new_sha": new_sha,
                "provider": plan.provider,
                "summary": plan.summary,
                "attempt": attempts,
            },
        )
