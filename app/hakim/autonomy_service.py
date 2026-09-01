"""Authenticated always-on HTTP ingress service for Ω APEX autonomy."""
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
from hashlib import sha256
import json
import threading
from typing import Callable

from .ingress_supervisor import AutonomousSupervisor, EventIngress, GitHubEventAdapter, RuntimeEventAdapter


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

    def __init__(self, ingress: EventIngress, github_secret: str, runtime_token: str):
        self.ingress = ingress
        self.github_secret = github_secret
        self.runtime_token = runtime_token
        self.github = GitHubEventAdapter()
        self.runtime = RuntimeEventAdapter()

    @staticmethod
    def _json(body: bytes) -> dict[str, object]:
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def github_webhook(self, headers: dict[str, str], body: bytes) -> ServiceResult:
        if not verify_github_signature(self.github_secret, body, headers.get("x-hub-signature-256")):
            return ServiceResult(401, "invalid signature")
        delivery = headers.get("x-github-delivery", "")
        event_name = headers.get("x-github-event", "")
        if not delivery or not event_name:
            return ServiceResult(400, "missing GitHub event headers")
        try:
            event = self.github.translate(delivery, event_name, self._json(body))
        except (ValueError, json.JSONDecodeError):
            return ServiceResult(400, "invalid payload")
        if event is None:
            return ServiceResult(202, "ignored")
        return ServiceResult(202, "accepted" if self.ingress.accept(event) else "duplicate")

    def runtime_webhook(self, headers: dict[str, str], body: bytes) -> ServiceResult:
        auth = headers.get("authorization", "")
        expected = f"Bearer {self.runtime_token}"
        if not self.runtime_token or not hmac.compare_digest(auth, expected):
            return ServiceResult(401, "invalid token")
        try:
            payload = self._json(body)
            source_id = str(payload.pop("source_id"))
            event_name = str(payload.pop("event_name"))
            subject = str(payload.pop("subject"))
            event = self.runtime.translate(source_id, event_name, subject, payload)
        except (KeyError, ValueError, json.JSONDecodeError):
            return ServiceResult(400, "invalid payload")
        if event is None:
            return ServiceResult(202, "ignored")
        return ServiceResult(202, "accepted" if self.ingress.accept(event) else "duplicate")


class AutonomyService:
    """Runs webhook ingress and the durable supervisor in one restart-safe process."""

    def __init__(self, app: AutonomyWebhookApplication, supervisor: AutonomousSupervisor, host: str = "127.0.0.1", port: int = 0):
        self.app = app
        self.supervisor = supervisor
        self.host = host
        self.port = port
        self._stop = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._server: ThreadingHTTPServer | None = None

    def _handler(self):
        app = self.app

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, result: ServiceResult) -> None:
                payload = json.dumps({"message": result.message}).encode("utf-8")
                self.send_response(result.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path == "/healthz":
                    self._reply(ServiceResult(200, "ok"))
                else:
                    self._reply(ServiceResult(404, "not found"))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                headers = {k.lower(): v for k, v in self.headers.items()}
                if self.path == "/webhooks/github":
                    self._reply(app.github_webhook(headers, body))
                elif self.path == "/events/runtime":
                    self._reply(app.runtime_webhook(headers, body))
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
