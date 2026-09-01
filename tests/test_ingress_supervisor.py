from app.hakim.durable_worker import DurableContinuationWorker, DurableWorkQueue
from app.hakim.event_continuation import ActionCandidate, EventDrivenContinuation, EventType
from app.hakim.ingress_supervisor import AutonomousSupervisor, EventIngress, GitHubEventAdapter, RuntimeEventAdapter


def engine(seen):
    return EventDrivenContinuation(
        lambda event: [ActionCandidate("continue", 1, True, True, True)],
        lambda action, event: seen.append((event.event_type, event.subject)),
    )


def test_github_workflow_success_is_normalized():
    event = GitHubEventAdapter().translate(
        "delivery-1",
        "workflow_run",
        {"action": "completed", "workflow_run": {"conclusion": "success", "head_sha": "abc"}},
    )
    assert event.event_type == EventType.CI_SUCCEEDED
    assert event.subject == "abc"


def test_github_merged_pr_is_normalized():
    event = GitHubEventAdapter().translate(
        "delivery-2",
        "pull_request",
        {"action": "closed", "pull_request": {"merged": True, "number": 8}},
    )
    assert event.event_type == EventType.PR_MERGED
    assert event.subject == "8"


def test_runtime_events_have_stable_dedup_identity():
    adapter = RuntimeEventAdapter()
    first = adapter.translate("runtime-a", "task.completed", "task-1", {"x": 1})
    second = adapter.translate("runtime-a", "task.completed", "task-1", {"x": 1})
    assert first.event_id == second.event_id
    assert first.event_type == EventType.TASK_COMPLETED


def test_ingress_and_supervisor_execute_event_end_to_end(tmp_path):
    queue = DurableWorkQueue(tmp_path / "omega.db")
    seen = []
    event = RuntimeEventAdapter().translate("runtime", "checkpoint.saved", "cp-1")
    ingress = EventIngress(queue)
    assert ingress.accept(event)
    assert not ingress.accept(event)

    worker = DurableContinuationWorker(queue, engine(seen), "worker-1")
    report = AutonomousSupervisor(worker).drain()
    assert report.processed == 1
    assert report.idle
    assert seen == [(EventType.CHECKPOINT_SAVED, "cp-1")]
    assert queue.get(event.event_id).status == "completed"


def test_supervisor_max_items_bounds_single_drain(tmp_path):
    queue = DurableWorkQueue(tmp_path / "omega.db")
    seen = []
    ingress = EventIngress(queue)
    adapter = RuntimeEventAdapter()
    for i in range(3):
        ingress.accept(adapter.translate("runtime", "task.completed", f"task-{i}"))
    report = AutonomousSupervisor(DurableContinuationWorker(queue, engine(seen), "w")).drain(max_items=2)
    assert report.processed == 2
    assert not report.idle
    assert len(seen) == 2


def test_heartbeat_generated_continuation_runs_in_same_drain(tmp_path):
    queue = DurableWorkQueue(tmp_path / "omega.db")
    seen = []
    generated = {"done": False}

    def heartbeat():
        if generated["done"]:
            return
        generated["done"] = True
        queue.enqueue("heartbeat-next", EventType.MANUAL_SIGNAL.value, "next-goal", {"source": "liveness"})

    worker = DurableContinuationWorker(queue, engine(seen), "w-live")
    report = AutonomousSupervisor(worker, heartbeat=heartbeat).drain(max_items=10)

    assert report.idle
    assert report.processed == 1
    assert report.heartbeat_resumes == 1
    assert seen == [(EventType.MANUAL_SIGNAL, "next-goal")]
    assert queue.get("heartbeat-next").status == "completed"


def test_liveness_resume_still_obeys_hard_work_budget(tmp_path):
    queue = DurableWorkQueue(tmp_path / "omega.db")
    seen = []
    counter = {"n": 0}

    def heartbeat():
        counter["n"] += 1
        queue.enqueue(
            f"live-{counter['n']}",
            EventType.MANUAL_SIGNAL.value,
            f"goal-{counter['n']}",
            {"source": "liveness"},
        )

    worker = DurableContinuationWorker(queue, engine(seen), "w-budget")
    report = AutonomousSupervisor(worker, heartbeat=heartbeat).drain(max_items=3)

    assert report.processed == 3
    assert not report.idle
    assert report.heartbeat_resumes >= 1
    assert len(seen) == 3
