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
    """Normalizes selected GitHub webhook events into Ω continuation events."""

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
            return IngressEvent(delivery_id, event_type, subject, payload)
        if event_name == "pull_request" and action == "closed":
            pr = payload.get("pull_request", {})
            if isinstance(pr, dict) and bool(pr.get("merged")):
                subject = str(pr.get("number") or pr.get("id") or "pull-request")
                return IngressEvent(delivery_id, EventType.PR_MERGED, subject, payload)
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
