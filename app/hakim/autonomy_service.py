"""Authenticated always-on HTTP ingress and end-user service for Ω APEX autonomy."""
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
from hashlib import sha256
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

from .end_user_tasks import EndUserTaskStore
from .ingress_supervisor import AutonomousSupervisor, EventIngress, GitHubEventAdapter, RuntimeEventAdapter


DEFAULT_MAX_BODY_BYTES = 1_048_576


def verify_github_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


@dataclass(frozen=True)
class ServiceResult:
    status: int
    message: str


class AutonomyWebhookApplication:
    """Pure request handler; HTTP transport is intentionally thin."""

    def __init__(
        self,
        ingress: EventIngress,
        github_secret: str,
        runtime_token: str,
        *,
        tasks: EndUserTaskStore | None = None,
        artifact_root: str | Path | None = None,
    ):
        self.ingress = ingress
        self.github_secret = github_secret
        self.runtime_token = runtime_token
        self.github = GitHubEventAdapter()
        self.runtime = RuntimeEventAdapter()
        self.tasks = tasks
        self.artifact_root = None if artifact_root is None else Path(artifact_root)
        if self.artifact_root is not None:
            self.artifact_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _json(body: bytes) -> dict[str, object]:
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def authorized(self, headers: dict[str, str]) -> bool:
        auth = headers.get("authorization", "")
        expected = f"Bearer {self.runtime_token}"
        return bool(self.runtime_token) and hmac.compare_digest(auth, expected)

    def github_webhook(self, headers: dict[str, str], body: bytes) -> ServiceResult:
        if not verify_github_signature(self.github_secret, body, headers.get("x-hub-signature-256")):
            return ServiceResult(401, "invalid signature")
        delivery = headers.get("x-github-delivery", "")
        event_name = headers.get("x-github-event", "")
        if not delivery or not event_name:
            return ServiceResult(400, "missing GitHub event headers")
        try:
            event = self.github.translate(delivery, event_name, self._json(body))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return ServiceResult(400, "invalid payload")
        if event is None:
            return ServiceResult(202, "ignored")
        return ServiceResult(202, "accepted" if self.ingress.accept(event) else "duplicate")

    def runtime_webhook(self, headers: dict[str, str], body: bytes) -> ServiceResult:
        if not self.authorized(headers):
            return ServiceResult(401, "invalid token")
        try:
            payload = self._json(body)
            source_id = str(payload.pop("source_id"))
            event_name = str(payload.pop("event_name"))
            subject = str(payload.pop("subject"))
            event = self.runtime.translate(source_id, event_name, subject, payload)
        except (KeyError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return ServiceResult(400, "invalid payload")
        if event is None:
            return ServiceResult(202, "ignored")
        return ServiceResult(202, "accepted" if self.ingress.accept(event) else "duplicate")

    def submit_task(self, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, object]]:
        if not self.authorized(headers):
            return 401, {"message": "invalid token"}
        if self.tasks is None:
            return 503, {"message": "end-user task service unavailable"}
        try:
            payload = self._json(body)
            prompt = payload.get("prompt")
            if not isinstance(prompt, str):
                raise ValueError("prompt is required")
            idem = headers.get("idempotency-key")
            if idem is None and isinstance(payload.get("idempotency_key"), str):
                idem = str(payload["idempotency_key"])
            task, created = self.tasks.submit(prompt, idempotency_key=idem)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return 400, {"message": str(exc)}
        value = task.public_dict()
        value["created"] = created
        return (202 if created else 200), value

    def task_status(self, headers: dict[str, str], task_id: str) -> tuple[int, dict[str, object]]:
        if not self.authorized(headers):
            return 401, {"message": "invalid token"}
        if self.tasks is None:
            return 503, {"message": "end-user task service unavailable"}
        task = self.tasks.get(task_id)
        if task is None:
            return 404, {"message": "task not found"}
        return 200, task.public_dict()

    def artifact(self, headers: dict[str, str], task_id: str) -> tuple[int, bytes, str, str] | None:
        if not self.authorized(headers) or self.tasks is None or self.artifact_root is None:
            return None
        task = self.tasks.get(task_id)
        if task is None or not task.artifact_name:
            return None
        candidate = (self.artifact_root / task.artifact_name).resolve()
        root = self.artifact_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return (
            200,
            candidate.read_bytes(),
            task.artifact_media_type or "application/octet-stream",
            task.artifact_name,
        )


class AutonomyService:
    """Runs webhook ingress, end-user API and durable supervisor in one restart-safe process."""

    def __init__(
        self,
        app: AutonomyWebhookApplication,
        supervisor: AutonomousSupervisor,
        host: str = "127.0.0.1",
        port: int = 0,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        ui_path: str | Path | None = None,
    ):
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.supervisor = supervisor
        self.host = host
        self.port = port
        self.max_body_bytes = max_body_bytes
        self.ui_path = None if ui_path is None else Path(ui_path)
        self._stop = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._server: ThreadingHTTPServer | None = None

    def _handler(self):
        app = self.app
        max_body_bytes = self.max_body_bytes
        ui_path = self.ui_path

        class Handler(BaseHTTPRequestHandler):
            def _headers(self) -> dict[str, str]:
                return {k.lower(): v for k, v in self.headers.items()}

            def _json_reply(self, status: int, value: dict[str, object]) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _reply(self, result: ServiceResult) -> None:
                self._json_reply(result.status, {"message": result.message})

            def _serve_ui(self) -> None:
                if ui_path is None or not ui_path.is_file():
                    self._reply(ServiceResult(404, "not found"))
                    return
                payload = ui_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _serve_artifact(self, task_id: str) -> None:
                artifact = app.artifact(self._headers(), task_id)
                if artifact is None:
                    self._reply(ServiceResult(404, "artifact not found"))
                    return
                status, payload, media_type, name = artifact
                safe_name = name.replace('"', "")
                self.send_response(status)
                self.send_header("Content-Type", media_type)
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == "/":
                    self._serve_ui()
                    return
                if path == "/healthz":
                    self._reply(ServiceResult(200, "ok"))
                    return
                if path.startswith("/tasks/"):
                    parts = [part for part in path.split("/") if part]
                    if len(parts) == 2:
                        status, value = app.task_status(self._headers(), parts[1])
                        self._json_reply(status, value)
                        return
                    if len(parts) == 3 and parts[2] == "artifact":
                        self._serve_artifact(parts[1])
                        return
                self._reply(ServiceResult(404, "not found"))

            def _read_bounded_body(self) -> bytes | None:
                if self.headers.get("Transfer-Encoding"):
                    self._reply(ServiceResult(400, "unsupported transfer encoding"))
                    return None
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    self._reply(ServiceResult(411, "content length required"))
                    return None
                try:
                    length = int(raw_length)
                except ValueError:
                    self._reply(ServiceResult(400, "invalid content length"))
                    return None
                if length < 0:
                    self._reply(ServiceResult(400, "invalid content length"))
                    return None
                if length > max_body_bytes:
                    self._reply(ServiceResult(413, "payload too large"))
                    return None
                return self.rfile.read(length)

            def do_POST(self):
                body = self._read_bounded_body()
                if body is None:
                    return
                path = urlsplit(self.path).path
                headers = self._headers()
                if path == "/webhooks/github":
                    self._reply(app.github_webhook(headers, body))
                elif path == "/events/runtime":
                    self._reply(app.runtime_webhook(headers, body))
                elif path == "/tasks":
                    status, value = app.submit_task(headers, body)
                    self._json_reply(status, value)
                else:
                    self._reply(ServiceResult(404, "not found"))

            def log_message(self, format, *args):
                return

        return Handler

    def start(self, poll_interval: float = 0.25) -> tuple[str, int]:
        if self._server is not None:
            raise RuntimeError("service already started")
        self._stop.clear()
        self._worker_thread = threading.Thread(
            target=self.supervisor.serve_forever,
            kwargs={"poll_interval": poll_interval, "stop": self._stop.is_set},
            daemon=True,
        )
        self._worker_thread.start()
        self._server = ThreadingHTTPServer((self.host, self.port), self._handler())
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        return self._server.server_address

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2)
            self._worker_thread = None
