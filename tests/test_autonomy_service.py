import hashlib
import hmac
import json
from urllib.error import HTTPError
import urllib.request

from app.hakim.autonomy_service import AutonomyService, AutonomyWebhookApplication, verify_github_signature
from app.hakim.durable_worker import DurableContinuationWorker, DurableWorkQueue
from app.hakim.event_continuation import ActionCandidate, EventDrivenContinuation
from app.hakim.ingress_supervisor import AutonomousSupervisor, EventIngress


def signed(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_service(tmp_path, seen, max_body_bytes=1_048_576):
    queue = DurableWorkQueue(tmp_path / "omega.db")
    engine = EventDrivenContinuation(
        lambda event: [ActionCandidate("continue", 1, True, True, True)],
        lambda action, event: seen.append(event.subject),
    )
    supervisor = AutonomousSupervisor(DurableContinuationWorker(queue, engine, "w1"))
    app = AutonomyWebhookApplication(EventIngress(queue), "secret", "runtime-token")
    return AutonomyService(app, supervisor, max_body_bytes=max_body_bytes)


def test_github_signature_verification():
    body = b"{}"
    assert verify_github_signature("s", body, signed("s", body))
    assert not verify_github_signature("s", body, signed("wrong", body))


def test_invalid_github_signature_is_rejected(tmp_path):
    app = make_service(tmp_path, []).app
    result = app.github_webhook({"x-hub-signature-256": "sha256=bad"}, b"{}")
    assert result.status == 401


def test_invalid_utf8_payload_fails_closed(tmp_path):
    app = make_service(tmp_path, []).app
    body = b"\xff\xfe"
    result = app.github_webhook(
        {
            "x-hub-signature-256": signed("secret", body),
            "x-github-delivery": "d",
            "x-github-event": "workflow_run",
        },
        body,
    )
    assert result.status == 400


def test_service_health_and_github_ingress_end_to_end(tmp_path):
    seen = []
    service = make_service(tmp_path, seen)
    host, port = service.start(poll_interval=0.01)
    try:
        health = urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=3)
        assert health.status == 200
        assert health.headers["X-Content-Type-Options"] == "nosniff"
        body = json.dumps({"action": "completed", "workflow_run": {"conclusion": "success", "head_sha": "abc"}}).encode()
        req = urllib.request.Request(
            f"http://{host}:{port}/webhooks/github",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signed("secret", body),
                "X-GitHub-Delivery": "delivery-1",
                "X-GitHub-Event": "workflow_run",
            },
        )
        response = urllib.request.urlopen(req, timeout=3)
        assert response.status == 202
        import time
        deadline = time.time() + 2
        while time.time() < deadline and seen != ["abc"]:
            time.sleep(0.01)
        assert seen == ["abc"]
    finally:
        service.stop()


def test_oversized_body_is_rejected_before_processing(tmp_path):
    seen = []
    service = make_service(tmp_path, seen, max_body_bytes=64)
    host, port = service.start(poll_interval=0.01)
    try:
        body = b"x" * 65
        req = urllib.request.Request(
            f"http://{host}:{port}/events/runtime",
            data=body,
            method="POST",
            headers={"Authorization": "Bearer runtime-token"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
            assert False, "oversized request must fail"
        except HTTPError as exc:
            assert exc.code == 413
        assert seen == []
    finally:
        service.stop()


def test_transfer_encoding_is_rejected(tmp_path):
    service = make_service(tmp_path, [])
    host, port = service.start(poll_interval=0.01)
    try:
        req = urllib.request.Request(
            f"http://{host}:{port}/events/runtime",
            data=b"{}",
            method="POST",
            headers={"Transfer-Encoding": "chunked", "Authorization": "Bearer runtime-token"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
            assert False, "unsupported framing must fail"
        except HTTPError as exc:
            assert exc.code == 400
    finally:
        service.stop()


def test_runtime_ingress_requires_bearer_token(tmp_path):
    app = make_service(tmp_path, []).app
    body = json.dumps({"source_id": "r", "event_name": "task.completed", "subject": "t"}).encode()
    assert app.runtime_webhook({}, body).status == 401
    assert app.runtime_webhook({"authorization": "Bearer runtime-token"}, body).status == 202
