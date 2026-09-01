"""Independent completion evidence auditor for Ω APEX goals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CompletionAudit:
    goal_id: str
    pr_number: int
    head_sha: str
    accepted: bool
    reasons: tuple[str, ...]
    acceptance: tuple[str, ...]
    workflow_count: int
    audited_at: str


class CompletionAuditor:
    KEY_PREFIX = "omega.completion_audit.v1."

    def __init__(self, runtime):
        self.runtime = runtime

    def audit_merged_goal(self, goal, pr_number: int) -> CompletionAudit:
        reasons = []
        if not goal.acceptance:
            reasons.append("goal has no acceptance criteria")
        pr = self.runtime.github.get_pull_request(pr_number)
        if not bool(pr.get("merged")):
            reasons.append("pull request is not confirmed merged")
        head = pr.get("head", {})
        observed_head = str(head.get("sha", "")) if isinstance(head, dict) else ""
        if not observed_head:
            reasons.append("pull request head SHA is missing")
        if goal.head_sha and observed_head and goal.head_sha != observed_head:
            reasons.append("merged pull request head does not match goal head")
        runs = self.runtime.github.workflow_runs_for_commit(observed_head) if observed_head else []
        if not runs:
            reasons.append("no workflow evidence found for merged goal head")
        else:
            if any(str(r.get("status")) != "completed" for r in runs):
                reasons.append("workflow evidence is incomplete")
            if any(str(r.get("conclusion")) not in {"success", "neutral", "skipped"} for r in runs):
                reasons.append("workflow evidence contains unacceptable conclusions")
        audit = CompletionAudit(
            goal_id=goal.goal_id,
            pr_number=pr_number,
            head_sha=observed_head,
            accepted=not reasons,
            reasons=tuple(reasons),
            acceptance=goal.acceptance,
            workflow_count=len(runs),
            audited_at=datetime.now(timezone.utc).isoformat(),
        )
        self.runtime.state.set_state(
            self.KEY_PREFIX + goal.goal_id,
            {
                "goal_id": audit.goal_id,
                "pr_number": audit.pr_number,
                "head_sha": audit.head_sha,
                "accepted": audit.accepted,
                "reasons": list(audit.reasons),
                "acceptance": list(audit.acceptance),
                "workflow_count": audit.workflow_count,
                "audited_at": audit.audited_at,
            },
        )
        return audit
