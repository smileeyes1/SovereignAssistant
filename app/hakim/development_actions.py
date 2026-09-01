"""Concrete autonomous GitHub development actions for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass

from .core import ActionRisk
from .event_continuation import ContinuationEvent, EventType
from .production import ProductionRuntime
from .recovery_governor import RegisteredAction, strong_claim


@dataclass
class AutonomousDevelopmentActions:
    runtime: ProductionRuntime

    def install(self) -> None:
        self.runtime.registry.register(
            RegisteredAction(
                name="merge-verified-pr",
                event_types=(EventType.CI_SUCCEEDED,),
                value=100,
                risk=ActionRisk.MODERATE,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("GitHub reported CI success", "github-webhook"),
                executor=self.merge_verified_pr,
                ready=lambda event: self.runtime.config.allow_merge,
            )
        )
        self.runtime.registry.register(
            RegisteredAction(
                name="record-ci-failure",
                event_types=(EventType.CI_FAILED,),
                value=20,
                risk=ActionRisk.LOW,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("GitHub reported CI failure", "github-webhook"),
                executor=self.record_ci_failure,
            )
        )
        self.runtime.registry.register(
            RegisteredAction(
                name="record-pr-merged",
                event_types=(EventType.PR_MERGED,),
                value=10,
                risk=ActionRisk.LOW,
                reversible=True,
                requires_human_approval=False,
                claim_factory=lambda event: strong_claim("GitHub reported PR merge", "github-webhook"),
                executor=self.record_pr_merged,
            )
        )

    def _workflow_run(self, event: ContinuationEvent) -> dict[str, object]:
        value = event.payload.get("workflow_run", {})
        return value if isinstance(value, dict) else {}

    def _candidate_pr_number(self, event: ContinuationEvent) -> int:
        run = self._workflow_run(event)
        pull_requests = run.get("pull_requests", [])
        if isinstance(pull_requests, list):
            for item in pull_requests:
                if isinstance(item, dict) and item.get("number") is not None:
                    return int(item["number"])
        discovered = self.runtime.github.pull_requests_for_commit(event.subject)
        open_prs = [item for item in discovered if str(item.get("state", "open")) == "open"]
        if len(open_prs) != 1:
            raise RuntimeError(f"expected exactly one open PR for commit, found {len(open_prs)}")
        return int(open_prs[0]["number"])

    def merge_verified_pr(self, event: ContinuationEvent) -> None:
        if not self.runtime.config.allow_merge:
            raise PermissionError("autonomous merge is disabled")
        number = self._candidate_pr_number(event)
        pr = self.runtime.github.get_pull_request(number)
        if str(pr.get("state")) != "open":
            raise RuntimeError("pull request is not open")
        head = pr.get("head", {})
        head_sha = str(head.get("sha", "")) if isinstance(head, dict) else ""
        if not head_sha or head_sha != event.subject:
            raise RuntimeError("PR head does not match verified workflow head")
        if pr.get("mergeable") is False:
            raise RuntimeError("pull request is not mergeable")

        runs = self.runtime.github.workflow_runs_for_commit(head_sha)
        if not runs:
            raise RuntimeError("no workflow evidence found for PR head")
        incomplete = [r for r in runs if str(r.get("status")) != "completed"]
        failed = [r for r in runs if str(r.get("conclusion")) not in {"success", "neutral", "skipped"}]
        if incomplete or failed:
            raise RuntimeError("not all workflow runs are complete and acceptable")

        result = self.runtime.github.merge_pull_request(number, head_sha, "squash")
        if not bool(result.get("merged")):
            raise RuntimeError(f"GitHub did not merge PR {number}")
        self.runtime.state.set_state(
            "omega.development.last_merge",
            {"pr": number, "head_sha": head_sha, "merge_sha": result.get("sha")},
        )

    def record_ci_failure(self, event: ContinuationEvent) -> None:
        self.runtime.state.set_state(
            "omega.development.last_ci_failure",
            {"subject": event.subject, "payload": event.payload},
        )

    def record_pr_merged(self, event: ContinuationEvent) -> None:
        self.runtime.state.set_state(
            "omega.development.last_pr_merged_event",
            {"subject": event.subject, "payload": event.payload},
        )
