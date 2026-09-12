"""Event ingress adapters and restart-safe supervisor for Ω APEX autonomy."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Callable

from .durable_worker import DurableContinuationWorker, DurableWorkQueue
from .event_continuation import EventType


@dataclass(frozen=True)
class IngressEvent:
    event_id: str
    event_type: EventType
    subject: str
    payload: dict[str, object]


class GitHubEventAdapter:
    """Normalizes selected GitHub events into minimal durable continuation data.

    GitHub event envelopes can contain far more metadata than HAKIM needs to
    continue work. Durable state is intentionally allow-listed here, before it
    reaches SQLite or any persistence/cache layer. Downstream components fetch
    richer repository data from GitHub only when an authorized action actually
    needs it.
    """

    @staticmethod
    def _positive_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @classmethod
    def _minimal_pull_requests(cls, value: object) -> list[dict[str, int]]:
        if not isinstance(value, list):
            return []
        result: list[dict[str, int]] = []
        seen: set[int] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            number = cls._positive_int(item.get("number"))
            if number is None or number in seen:
                continue
            seen.add(number)
            result.append({"number": number})
        return result

    @classmethod
    def _workflow_run_payload(cls, run: dict[str, object]) -> dict[str, object]:
        minimal: dict[str, object] = {
            "conclusion": str(run.get("conclusion", "")),
            "head_sha": str(run.get("head_sha", "")),
            "pull_requests": cls._minimal_pull_requests(run.get("pull_requests", [])),
        }
        run_id = cls._positive_int(run.get("id"))
        if run_id is not None:
            minimal["id"] = run_id
        return {"action": "completed", "workflow_run": minimal}

    @classmethod
    def _pull_request_payload(cls, pr: dict[str, object]) -> dict[str, object]:
        minimal: dict[str, object] = {"merged": True}
        number = cls._positive_int(pr.get("number"))
        if number is not None:
            minimal["number"] = number
        merge_commit_sha = pr.get("merge_commit_sha")
        if isinstance(merge_commit_sha, str) and merge_commit_sha.strip():
            minimal["merge_commit_sha"] = merge_commit_sha.strip()
        return {"action": "closed", "pull_request": minimal}

    @classmethod
    def minimize_durable_payload(
        cls, event_type: EventType, payload: dict[str, object]
    ) -> dict[str, object]:
        """Return the complete allow-listed durable payload for one GitHub event.

        This method is deliberately strict so historical-state migrations and
        live ingress share exactly one privacy contract. Unknown event types are
        rejected rather than silently persisting an unreviewed envelope.
        """
        if event_type in {EventType.CI_SUCCEEDED, EventType.CI_FAILED}:
            run = payload.get("workflow_run", {})
            if not isinstance(run, dict):
                run = {}
            return cls._workflow_run_payload(run)
        if event_type == EventType.PR_MERGED:
            pr = payload.get("pull_request", {})
            if not isinstance(pr, dict):
                pr = {}
            return cls._pull_request_payload(pr)
        raise ValueError(f"unsupported GitHub durable event type: {event_type.value}")

    def translate(self, delivery_id: str, event_name: str, payload: dict[str, object]) -> IngressEvent | None:
        if not delivery_id.strip():
            raise ValueError("delivery_id is required")
        action = str(payload.get("action", ""))
        if event_name == "workflow_run":
            run = payload.get("workflow_run", {})
            if not isinstance(run, dict) or action != "completed":
                return None
            conclusion = str(run.get("conclusion", ""))
            event_type = EventType.CI_SUCCEEDED if conclusion == "success" else EventType.CI_FAILED
            subject = str(run.get("head_sha") or run.get("id") or "workflow-run")
            return IngressEvent(
                delivery_id,
                event_type,
                subject,
                self.minimize_durable_payload(event_type, payload),
            )
        if event_name == "pull_request" and action == "closed":
            pr = payload.get("pull_request", {})
            if isinstance(pr, dict) and bool(pr.get("merged")):
                subject = str(pr.get("number") or pr.get("id") or "pull-request")
                return IngressEvent(
                    delivery_id,
                    EventType.PR_MERGED,
                    subject,
                    self.minimize_durable_payload(EventType.PR_MERGED, payload),
                )
        return None


class RuntimeEventAdapter:
    """Normalizes runtime/task lifecycle signals."""

    MAP = {
        "task.completed": EventType.TASK_COMPLETED,
        "task.failed": EventType.TASK_FAILED,
        "checkpoint.saved": EventType.CHECKPOINT_SAVED,
        "capability.changed": EventType.CAPABILITY_CHANGED,
    }

    def translate(self, source_id: str, event_name: str, subject: str, payload: dict[str, object] | None = None) -> IngressEvent | None:
        event_type = self.MAP.get(event_name)
        if event_type is None:
            return None
        if not source_id.strip() or not subject.strip():
            raise ValueError("source_id and subject are required")
        canonical = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
        event_id = sha256(f"{source_id}\0{event_name}\0{subject}\0{canonical}".encode("utf-8")).hexdigest()
        return IngressEvent(event_id, event_type, subject, payload or {})


class EventIngress:
    def __init__(self, queue: DurableWorkQueue):
        self.queue = queue

    def accept(self, event: IngressEvent, max_attempts: int = 5) -> bool:
        return self.queue.enqueue(event.event_id, event.event_type.value, event.subject, event.payload, max_attempts=max_attempts)


@dataclass(frozen=True)
class SupervisorReport:
    processed: int
    idle: bool
    outcomes: tuple[str, ...]
    heartbeat_resumes: int = 0


class AutonomousSupervisor:
    """Drains durable work and immediately resumes work synthesized by its heartbeat.

    The liveness invariant is: an idle observation is not terminal until the
    heartbeat has had one opportunity to synthesize recovery/next-goal work and
    that work has been checked in the same drain cycle. max_items remains the
    hard anti-runaway budget.
    """

    def __init__(self, worker: DurableContinuationWorker, heartbeat: Callable[[], None] | None = None):
        self.worker = worker
        self.heartbeat = heartbeat or (lambda: None)

    def drain(self, max_items: int = 100) -> SupervisorReport:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        outcomes: list[str] = []
        heartbeat_resumes = 0
        while len(outcomes) < max_items:
            outcome = self.worker.run_once()
            if outcome != "idle":
                outcomes.append(outcome)
                continue

            # Idle is provisional: the heartbeat may discover an unfinished
            # mission and enqueue the next safe continuation event.
            self.heartbeat()
            resumed = self.worker.run_once()
            if resumed == "idle":
                return SupervisorReport(len(outcomes), True, tuple(outcomes), heartbeat_resumes)
            heartbeat_resumes += 1
            outcomes.append(resumed)

        self.heartbeat()
        return SupervisorReport(len(outcomes), False, tuple(outcomes), heartbeat_resumes)

    def serve_forever(self, poll_interval: float = 1.0, stop: Callable[[], bool] | None = None) -> None:
        if poll_interval < 0:
            raise ValueError("poll_interval must be non-negative")
        stop = stop or (lambda: False)
        while not stop():
            report = self.drain()
            if report.idle:
                time.sleep(poll_interval)
