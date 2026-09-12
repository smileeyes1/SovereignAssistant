import json

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
        {
            "action": "completed",
            "workflow_run": {
                "id": 42,
                "conclusion": "success",
                "head_sha": "abc",
                "pull_requests": [{"number": 17, "title": "must not persist"}],
            },
        },
    )
    assert event.event_type == EventType.CI_SUCCEEDED
    assert event.subject == "abc"
    assert event.payload == {
        "action": "completed",
        "workflow_run": {
            "id": 42,
            "conclusion": "success",
            "head_sha": "abc",
            "pull_requests": [{"number": 17}],
        },
    }


def test_github_workflow_payload_is_allowlisted_before_durable_ingress():
    event = GitHubEventAdapter().translate(
        "delivery-private",
        "workflow_run",
        {
            "action": "completed",
            "secret": "top-level-secret",
            "repository": {"private": True, "owner": {"email": "owner@example.invalid"}},
            "sender": {"login": "person", "email": "person@example.invalid"},
            "workflow_run": {
                "id": 99,
                "conclusion": "failure",
                "head_sha": "deadbeef",
                "head_branch": "private-branch-name",
                "actor": {"email": "actor@example.invalid", "token": "secret-token"},
                "pull_requests": [
                    {
                        "number": 8,
                        "title": "sensitive title",
                        "body": "sensitive body",
                        "user": {"email": "pr@example.invalid"},
                    },
                    {"number": 8, "body": "duplicate must collapse"},
                    {"number": "9", "unexpected": "drop me"},
                ],
                "future_unknown_field": {"credential": "future-secret"},
            },
        },
    )

    assert event.event_type == EventType.CI_FAILED
    assert event.subject == "deadbeef"
    assert event.payload == {
        "action": "completed",
        "workflow_run": {
            "id": 99,
            "conclusion": "failure",
            "head_sha": "deadbeef",
            "pull_requests": [{"number": 8}, {"number": 9}],
        },
    }
    durable_json = json.dumps(event.payload, sort_keys=True)
    for forbidden in (
        "top-level-secret",
        "owner@example.invalid",
        "person@example.invalid",
        "private-branch-name",
        "actor@example.invalid",
        "secret-token",
        "sensitive title",
        "sensitive body",
        "pr@example.invalid",
        "future-secret",
        "future_unknown_field",
    ):
        assert forbidden not in durable_json


def test_sqlite_queue_persists_only_minimized_github_payload(tmp_path):
    event = GitHubEventAdapter().translate(
        "delivery-db",
        "workflow_run",
        {
            "action": "completed",
            "workflow_run": {
                "id": 501,
                "conclusion": "failure",
                "head_sha": "sha501",
                "actor": {"email": "never-store@example.invalid"},
                "pull_requests": [{"number": 31, "body": "never-store-body"}],
            },
            "sender": {"token": "never-store-token"},
        },
    )
    queue = DurableWorkQueue(tmp_path / "omega.db")
    assert EventIngress(queue).accept(event)
    stored = queue.get("delivery-db")
    assert stored is not None
    assert stored.payload == {
        "action": "completed",
        "workflow_run": {
            "id": 501,
            "conclusion": "failure",
            "head_sha": "sha501",
            "pull_requests": [{"number": 31}],
        },
    }
    persisted_json = json.dumps(stored.payload, sort_keys=True)
    assert "never-store@example.invalid" not in persisted_json
    assert "never-store-body" not in persisted_json
    assert "never-store-token" not in persisted_json


def test_github_merged_pr_is_normalized():
    event = GitHubEventAdapter().translate(
        "delivery-2",
        "pull_request",
        {
            "action": "closed",
            "repository": {"owner": {"email": "owner@example.invalid"}},
            "pull_request": {
                "merged": True,
                "number": 8,
                "merge_commit_sha": "merge123",
                "title": "must not persist",
                "body": "must not persist either",
                "user": {"email": "author@example.invalid"},
            },
        },
    )
    assert event.event_type == EventType.PR_MERGED
    assert event.subject == "8"
    assert event.payload == {
        "action": "closed",
        "pull_request": {
            "merged": True,
            "number": 8,
            "merge_commit_sha": "merge123",
        },
    }
    durable_json = json.dumps(event.payload, sort_keys=True)
    assert "owner@example.invalid" not in durable_json
    assert "author@example.invalid" not in durable_json
    assert "must not persist" not in durable_json


def test_github_payload_minimizer_rejects_invalid_pr_numbers_and_unknown_events():
    adapter = GitHubEventAdapter()
    event = adapter.translate(
        "delivery-3",
        "workflow_run",
        {
            "action": "completed",
            "workflow_run": {
                "id": "7",
                "conclusion": "startup_failure",
                "head_sha": "sha7",
                "pull_requests": [
                    {"number": True},
                    {"number": 0},
                    {"number": -4},
                    {"number": "bad"},
                    {"number": "12"},
                ],
            },
        },
    )
    assert event.payload["workflow_run"]["id"] == 7
    assert event.payload["workflow_run"]["pull_requests"] == [{"number": 12}]
    assert adapter.translate("delivery-4", "issues", {"action": "opened", "secret": "x"}) is None


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
