"""Ω APEX event-driven autonomous continuation primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable


class EventType(str, Enum):
    CI_SUCCEEDED = "ci_succeeded"
    CI_FAILED = "ci_failed"
    PR_MERGED = "pr_merged"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    CHECKPOINT_SAVED = "checkpoint_saved"
    CAPABILITY_CHANGED = "capability_changed"
    MANUAL_SIGNAL = "manual_signal"


@dataclass(frozen=True)
class ContinuationEvent:
    event_id: str
    event_type: EventType
    subject: str
    payload: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        if not self.subject.strip():
            raise ValueError("subject is required")


@dataclass(frozen=True)
class ActionCandidate:
    name: str
    value: float
    safe: bool
    reversible: bool
    authorized: bool
    ready: bool = True

    @property
    def executable(self) -> bool:
        return self.safe and self.reversible and self.authorized and self.ready


@dataclass(frozen=True)
class ContinuationDecision:
    event_id: str
    selected_action: str | None
    status: str
    reason: str


@dataclass
class EventDrivenContinuation:
    action_source: Callable[[ContinuationEvent], Iterable[ActionCandidate]]
    executor: Callable[[ActionCandidate, ContinuationEvent], None]
    processed_event_ids: set[str] = field(default_factory=set)
    decisions: list[ContinuationDecision] = field(default_factory=list)

    def handle(self, event: ContinuationEvent) -> ContinuationDecision:
        if event.event_id in self.processed_event_ids:
            decision = ContinuationDecision(event.event_id, None, "ignored", "duplicate event")
            self.decisions.append(decision)
            return decision
        candidates = sorted((c for c in self.action_source(event) if c.executable), key=lambda c: c.value, reverse=True)
        if not candidates:
            self.processed_event_ids.add(event.event_id)
            decision = ContinuationDecision(event.event_id, None, "blocked", "no safe reversible authorized ready action")
            self.decisions.append(decision)
            return decision
        selected = candidates[0]
        try:
            self.executor(selected, event)
        except Exception as exc:
            decision = ContinuationDecision(event.event_id, selected.name, "failed", f"executor failed: {type(exc).__name__}: {exc}")
            self.decisions.append(decision)
            return decision
        self.processed_event_ids.add(event.event_id)
        decision = ContinuationDecision(event.event_id, selected.name, "executed", "highest-value eligible action executed")
        self.decisions.append(decision)
        return decision


@dataclass
class EventRouter:
    handlers: list[Callable[[ContinuationEvent], ContinuationDecision]] = field(default_factory=list)

    def subscribe(self, handler: Callable[[ContinuationEvent], ContinuationDecision]) -> None:
        self.handlers.append(handler)

    def publish(self, event: ContinuationEvent) -> list[ContinuationDecision]:
        return [handler(event) for handler in tuple(self.handlers)]
