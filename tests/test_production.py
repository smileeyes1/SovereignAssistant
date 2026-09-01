import json
import urllib.request

import pytest

from app.hakim.core import ActionRisk
from app.hakim.event_continuation import EventType
from app.hakim.production import ProductionConfig, build_production_runtime
from app.hakim.recovery_governor import ActionRegistry, RegisteredAction, strong_claim


def config(tmp_path, **changes):
    data = dict(
        database_path=tmp_path / "omega.db",
        worker_id="w1",
        repository="owner/repo",
        github_token="token",
        github_webhook_secret="secret",
        runtime_token="runtime",
        host="127.0.0.1",
        port=8080,
    )
    data.update(changes)
    return ProductionConfig(**data)


def test_env_requires_security_credentials():
    with pytest.raises(ValueError, match="OMEGA_REPOSITORY"):
        ProductionConfig.from_env({})
    env = {
        "OMEGA_REPOSITORY": "o/r",
        "OMEGA_GITHUB_TOKEN": "t",
        "OMEGA_GITHUB_WEBHOOK_SECRET": "s",
        "OMEGA_RUNTIME_TOKEN": "r",
        "OMEGA_ALLOW_MERGE": "true",
    }
    cfg = ProductionConfig.from_env(env)
    assert cfg.repository == "o/r"
    assert cfg.allow_merge is True
    assert cfg.allow_branch_create is True


def test_production_runtime_wires_durable_governed_execution(tmp_path):
    seen = []
    registry = ActionRegistry()
    registry.register(
        RegisteredAction(
            name="on-task-complete",
            event_types=(EventType.TASK_COMPLETED,),
            value=10,
            risk=ActionRisk.LOW,
            reversible=True,
            requires_human_approval=False,
            claim_factory=lambda event: strong_claim("task completion observed"),
            executor=lambda event: seen.append(event.subject),
        )
    )
    runtime = build_production_runtime(config(tmp_path), registry)
    event = runtime.service.app.runtime.translate("source", "task.completed", "task-1", {})
    assert runtime.service.app.ingress.accept(event)
    report = runtime.service.supervisor.drain()
    assert report.processed == 1
    assert seen == ["task-1"]
    assert runtime.queue.get(event.event_id).status == "completed"


def test_github_write_policy_flows_from_production_config(tmp_path):
    runtime = build_production_runtime(config(tmp_path, allow_merge=False))
    assert runtime.github.policy.allow_merge is False
    runtime2 = build_production_runtime(config(tmp_path, database_path=tmp_path / "two.db", allow_merge=True))
    assert runtime2.github.policy.allow_merge is True


def test_production_service_can_start_and_report_health(tmp_path):
    runtime = build_production_runtime(config(tmp_path, port=0))
    host, port = runtime.start()
    try:
        response = urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=3)
        assert response.status == 200
        payload = json.loads(response.read().decode())
        assert payload["message"] == "ok"
    finally:
        runtime.stop()
