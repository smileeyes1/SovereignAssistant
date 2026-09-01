"""Closed-loop goal continuation for Ω APEX."""
from __future__ import annotations

from .event_continuation import ContinuationEvent
from .goal_governor import AutonomousGoalGovernor


class ClosedLoopGoalGovernor(AutonomousGoalGovernor):
    """Completes a merged goal and immediately attempts the next ready goal."""

    def complete_merged_goal(self, event: ContinuationEvent) -> None:
        before = self.portfolio.active()
        super().complete_merged_goal(event)
        after = self.portfolio.active()
        # Only advance when this merge actually closed an active portfolio goal.
        if before and not after:
            self.advance(event)
