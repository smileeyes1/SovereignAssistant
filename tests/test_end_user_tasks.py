import json
from pathlib import Path
from urllib.error import HTTPError
import urllib.request

from app.hakim.autonomy_service import AutonomyService, AutonomyWebhookApplication
from app.hakim.durable_worker import DurableContinuationWorker, DurableWorkQueue
from app.hakim.end_user_tasks import EndUserTaskStore
from app.hakim.event_continuation import ActionCandidate, EventDrivenContinuation
from app.hakim.ingress_supervisor import AutonomousSupervisor, EventIngress


def make_service(tmp_path):
    db = tmp_path / "omega.db"
    queue = DurableWorkQueue(db)
    engine = EventDrivenContinuation(
        lambda event: [ActionCandidate("continue", 1, True, True, True)],
        lambda action, event: None,
    )
    supervisor = AutonomousSupervisor(DurableContinuationWorker(queue, engine, "w1"))
    tasks = EndUserTaskStore(db)
    artifacts = tmp_path / "artifacts"
    app = AutonomyWebhookApplication(
        EventIngress(queue),
        "secret",
        "runtime-token",
        tasks=tasks,
        artifact_root=artifacts,
    )
    ui = tmp_path / "index.html"
    ui.write_text("<!doctype html><title>HAKIM</title>", encoding="utf-8")
    return AutonomyService(app, supervisor, ui_path=ui), tasks, artifacts


def auth():
    return {"Authorization": "Bearer runtime-token"}


def test_task_store_is_durable_and_idempotent(tmp_path):
    db = tmp_path / "omega.db"
    first = EndUserTaskStore(db)
    task, created = first.submit("أنشئ ملفًا", idempotency_key="same-request")
    assert created
    second = EndUserTaskStore(db)
    restored = second.get(task.task_id)
    assert restored is not None
    assert restored.prompt == "أنشئ ملفًا"
    duplicate, created_again = second.submit("لن ينشئ مهمة جديدة", idempotency_key="same-request")
    assert not created_again
    assert duplicate.task_id == task.task_id


def test_task_http_submit_status_and_auth(tmp_path):
    service, tasks, _ = make_service(tmp_path)
    host, port = service.start(poll_interval=0.01)
    try:
        body = json.dumps({"prompt": "أنشئ درس الجمع ضمن ١٠ كملف PDF"}).encode("utf-8")
        unauth = urllib.request.Request(
            f"http://{host}:{port}/tasks",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(unauth, timeout=3)
            assert False, "unauthenticated task submission must fail"
        except HTTPError as exc:
            assert exc.code == 401

        req = urllib.request.Request(
            f"http://{host}:{port}/tasks",
            data=body,
            method="POST",
            headers={**auth(), "Content-Type": "application/json", "Idempotency-Key": "acceptance-1"},
        )
        response = urllib.request.urlopen(req, timeout=3)
        assert response.status == 202
        created = json.loads(response.read().decode("utf-8"))
        assert created["status"] == "queued"
        assert created["created"] is True

        status_req = urllib.request.Request(f"http://{host}:{port}/tasks/{created['task_id']}", headers=auth())
        status = json.loads(urllib.request.urlopen(status_req, timeout=3).read().decode("utf-8"))
        assert status["prompt"] == "أنشئ درس الجمع ضمن ١٠ كملف PDF"
        assert status["verified"] is False
        assert tasks.get(created["task_id"]) is not None
    finally:
        service.stop()


def test_completed_artifact_is_downloadable_and_exact(tmp_path):
    service, tasks, artifacts = make_service(tmp_path)
    task, _ = tasks.submit("اصنع ملفًا")
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = b"%PDF-1.4\n% end-user acceptance artifact\n"
    (artifacts / "result.pdf").write_bytes(payload)
    tasks.complete(
        task.task_id,
        result={"message": "ready"},
        artifact_name="result.pdf",
        artifact_media_type="application/pdf",
        verified=True,
    )
    host, port = service.start(poll_interval=0.01)
    try:
        status_req = urllib.request.Request(f"http://{host}:{port}/tasks/{task.task_id}", headers=auth())
        status = json.loads(urllib.request.urlopen(status_req, timeout=3).read().decode("utf-8"))
        assert status["status"] == "completed"
        assert status["verified"] is True
        assert status["artifact"]["url"] == f"/tasks/{task.task_id}/artifact"
        artifact_req = urllib.request.Request(f"http://{host}:{port}/tasks/{task.task_id}/artifact", headers=auth())
        artifact = urllib.request.urlopen(artifact_req, timeout=3)
        assert artifact.headers["Content-Type"] == "application/pdf"
        assert artifact.read() == payload
    finally:
        service.stop()


def test_root_serves_real_ui_from_runtime(tmp_path):
    service, _, _ = make_service(tmp_path)
    host, port = service.start(poll_interval=0.01)
    try:
        response = urllib.request.urlopen(f"http://{host}:{port}/", timeout=3)
        assert response.status == 200
        assert b"HAKIM" in response.read()
    finally:
        service.stop()
