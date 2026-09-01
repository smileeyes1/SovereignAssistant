from app.hakim.durable_worker import DurableContinuationWorker, DurableWorkQueue
from app.hakim.event_continuation import ActionCandidate, ContinuationEvent, EventDrivenContinuation, EventType


def make_engine(executor):
    return EventDrivenContinuation(
        lambda event: [ActionCandidate("continue", 1, True, True, True)],
        executor,
    )


def test_queue_is_idempotent_and_restart_safe(tmp_path):
    db = tmp_path / "omega.db"
    q1 = DurableWorkQueue(db)
    assert q1.enqueue("evt-1", EventType.TASK_COMPLETED.value, "task")
    assert not q1.enqueue("evt-1", EventType.TASK_COMPLETED.value, "task")
    q2 = DurableWorkQueue(db)
    assert q2.get("evt-1").status == "pending"


def test_worker_completes_durable_event(tmp_path):
    q = DurableWorkQueue(tmp_path / "omega.db")
    seen = []
    q.enqueue("evt-2", EventType.CI_SUCCEEDED.value, "pr-7")
    worker = DurableContinuationWorker(q, make_engine(lambda action, event: seen.append(event.subject)), "w1")
    assert worker.run_once() == "executed"
    assert seen == ["pr-7"]
    assert q.get("evt-2").status == "completed"


def test_transient_failure_retries_then_completes(tmp_path):
    q = DurableWorkQueue(tmp_path / "omega.db")
    q.enqueue("evt-3", EventType.TASK_FAILED.value, "task", max_attempts=3)
    attempts = {"n": 0}

    def execute(action, event):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("temporary")

    worker = DurableContinuationWorker(q, make_engine(execute), "w1", backoff=lambda n: 0)
    assert worker.run_once() == "pending"
    assert worker.run_once() == "executed"
    assert q.get("evt-3").status == "completed"
    assert q.get("evt-3").attempts == 2


def test_permanent_failure_dead_letters(tmp_path):
    q = DurableWorkQueue(tmp_path / "omega.db")
    q.enqueue("evt-4", EventType.CI_FAILED.value, "build", max_attempts=2)

    def fail(action, event):
        raise RuntimeError("permanent")

    worker = DurableContinuationWorker(q, make_engine(fail), "w1", backoff=lambda n: 0)
    assert worker.run_once() == "pending"
    assert worker.run_once() == "dead"
    item = q.get("evt-4")
    assert item.status == "dead"
    assert item.attempts == 2
    assert "executor failed" in item.last_error


def test_expired_lease_is_recovered_after_crash(tmp_path):
    q = DurableWorkQueue(tmp_path / "omega.db")
    q.enqueue("evt-5", EventType.CHECKPOINT_SAVED.value, "checkpoint")
    claimed = q.claim("crashed", lease_seconds=1)
    assert claimed.status == "leased"
    with q._connect() as conn:
        conn.execute("UPDATE work_queue SET lease_until='2000-01-01T00:00:00+00:00' WHERE job_id='evt-5'")
    assert q.recover_expired_leases() == 1
    reclaimed = q.claim("replacement")
    assert reclaimed.job_id == "evt-5"
    assert reclaimed.lease_owner == "replacement"
