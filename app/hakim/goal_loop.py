"""Closed-loop goal continuation for Ω APEX."""
from __future__ import annotations

from .completion_auditor import CompletionAuditor
from .event_continuation import ContinuationEvent
from .goal_governor import AutonomousGoalGovernor


class ClosedLoopGoalGovernor(AutonomousGoalGovernor):
    """Completes a merged goal only after independent completion evidence passes."""

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

        audit = CompletionAuditor(self.runtime).audit_merged_goal(goal, number)
        if not audit.accepted:
            self.runtime.state.set_state(
                "omega.goals.last_completion_rejected",
                {"goal_id": goal.goal_id, "pr": number, "reasons": list(audit.reasons)},
            )
            return

        before = self.portfolio.active()
        super().complete_merged_goal(event)
        after = self.portfolio.active()
        if before and not after:
            self.advance(event)
