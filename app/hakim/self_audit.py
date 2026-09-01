"""Autonomous runtime self-audit and continuation recovery for Ω APEX."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time

from .capability_registry import CapabilityRegistry
from .event_continuation import EventType
from .goal_governor import GoalPortfolio
from .production import ProductionRuntime


@dataclass(frozen=True)
class SelfAuditReport:
    status: str
    blockers: tuple[str, ...]
    recovery_event: str | None
    checked_at: str


class AutonomySelfAuditor:
    KEY = "omega.self_audit.last"
    LAST_RUN_KEY = "omega.self_audit.last_run_epoch"

    def __init__(
        self,
        runtime: ProductionRuntime,
        capabilities: CapabilityRegistry | None = None,
        *,
        min_interval_seconds: float = 30.0,
        repair_budget: int = 3,
        required_provider: str = "openai-responses",
    ):
        self.runtime = runtime
        self.capabilities = capabilities or CapabilityRegistry(runtime.state)
        self.min_interval_seconds = min_interval_seconds
        self.repair_budget = repair_budget
        self.required_provider = required_provider

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _dead_work(self) -> list[dict[str, object]]:
        with self.runtime.queue._connect() as conn:
            rows = conn.execute(
                "SELECT job_id,event_type,subject,attempts,max_attempts,last_error FROM work_queue WHERE status='dead' ORDER BY updated_at,job_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def _pending_work_count(self) -> int:
        with self.runtime.queue._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM work_queue WHERE status IN ('pending','leased')"
            ).fetchone()
        return int(row["n"])

    def run_once(self, *, force: bool = False) -> SelfAuditReport:
        now_epoch = time.time()
        last_epoch = float(self.runtime.state.get_state(self.LAST_RUN_KEY, 0.0) or 0.0)
        if not force and now_epoch - last_epoch < self.min_interval_seconds:
            saved = self.runtime.state.get_state(self.KEY, {})
            if isinstance(saved, dict) and saved.get("status"):
                return SelfAuditReport(
                    str(saved["status"]),
                    tuple(str(x) for x in saved.get("blockers", [])),
                    None if saved.get("recovery_event") is None else str(saved["recovery_event"]),
                    str(saved.get("checked_at", self._now())),
                )

        blockers: list[str] = []
        dead = self._dead_work()
        for item in dead:
            blockers.append(
                f"dead work {item['job_id']} after {item['attempts']}/{item['max_attempts']} attempts: {item.get('last_error') or 'unknown error'}"
            )

        portfolio = GoalPortfolio(self.runtime)
        active = portfolio.active()
        for goal in active:
            if goal.pr_number is None or not goal.head_sha:
                blockers.append(f"active goal {goal.goal_id} is missing PR/head evidence")
                continue
            attempts = int(self.runtime.state.get_state(f"omega.ci_repair.pr.{goal.pr_number}.attempts", 0))
            if attempts >= self.repair_budget:
                blockers.append(f"repair budget exhausted for goal {goal.goal_id} PR #{goal.pr_number}: {attempts}/{self.repair_budget}")

        next_goal = portfolio.next_ready() if not active else None
        if next_goal is not None and not self.runtime.config.allow_file_write:
            blockers.append(
                f"mission incomplete: ready goal {next_goal.goal_id} exists but autonomous coding/file-write capability is unavailable"
            )
        elif self.runtime.config.allow_file_write and not self.capabilities.is_healthy(self.required_provider):
            health = self.capabilities.get(self.required_provider)
            blockers.append(
                f"required provider {self.required_provider} unhealthy after {health.failures} failures: {health.last_error or 'unknown error'}"
            )

        recovery_event = None
        status = "healthy"
        if blockers:
            status = "blocked"
        elif not active and self._pending_work_count() == 0 and next_goal is not None:
            recovery_event = f"omega-self-audit-continue-{next_goal.goal_id}"
            self.runtime.queue.enqueue(
                recovery_event,
                EventType.MANUAL_SIGNAL.value,
                "self-audit-continuation",
                {"source": "autonomy-self-audit", "goal_id": next_goal.goal_id},
                max_attempts=5,
            )
            status = "recovery_enqueued"

        report = SelfAuditReport(status, tuple(blockers), recovery_event, self._now())
        self.runtime.state.set_state(
            self.KEY,
            {
                "status": report.status,
                "blockers": list(report.blockers),
                "recovery_event": report.recovery_event,
                "checked_at": report.checked_at,
                "dead_work_count": len(dead),
                "active_goal_count": len(active),
                "next_ready_goal": None if next_goal is None else next_goal.goal_id,
                "mission_complete": next_goal is None and not active and not dead,
            },
        )
        self.runtime.state.set_state(self.LAST_RUN_KEY, now_epoch)
        return report
