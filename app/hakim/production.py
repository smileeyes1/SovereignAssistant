"""Production composition root for the Ω APEX sovereign autonomy runtime."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .autonomy_service import AutonomyService, AutonomyWebhookApplication
from .durable_state import DurableStateStore
from .durable_worker import DurableContinuationWorker, DurableWorkQueue
from .github_control import GitHubControl, GitHubWritePolicy
from .ingress_supervisor import AutonomousSupervisor, EventIngress
from .recovery_governor import ActionRegistry, RecoveryGovernor


@dataclass(frozen=True)
class ProductionConfig:
    database_path: Path
    worker_id: str
    repository: str
    github_token: str
    github_webhook_secret: str
    runtime_token: str
    host: str = "0.0.0.0"
    port: int = 8080
    allow_branch_create: bool = True
    allow_merge: bool = False
    allow_comment: bool = True

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ProductionConfig":
        values = os.environ if env is None else env

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise ValueError(f"{name} is required")
            return value

        def flag(name: str, default: bool) -> bool:
            raw = values.get(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        port = int(values.get("OMEGA_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError("OMEGA_PORT must be between 1 and 65535")
        return cls(
            database_path=Path(values.get("OMEGA_DB_PATH", ".omega/omega.db")),
            worker_id=values.get("OMEGA_WORKER_ID", "omega-worker-1").strip() or "omega-worker-1",
            repository=required("OMEGA_REPOSITORY"),
            github_token=required("OMEGA_GITHUB_TOKEN"),
            github_webhook_secret=required("OMEGA_GITHUB_WEBHOOK_SECRET"),
            runtime_token=required("OMEGA_RUNTIME_TOKEN"),
            host=values.get("OMEGA_HOST", "0.0.0.0"),
            port=port,
            allow_branch_create=flag("OMEGA_ALLOW_BRANCH_CREATE", True),
            allow_merge=flag("OMEGA_ALLOW_MERGE", False),
            allow_comment=flag("OMEGA_ALLOW_COMMENT", True),
        )


@dataclass
class ProductionRuntime:
    config: ProductionConfig
    state: DurableStateStore
    queue: DurableWorkQueue
    github: GitHubControl
    registry: ActionRegistry
    governor: RecoveryGovernor
    service: AutonomyService

    def start(self) -> tuple[str, int]:
        return self.service.start()

    def stop(self) -> None:
        self.service.stop()


def build_production_runtime(config: ProductionConfig, registry: ActionRegistry | None = None, github_opener=None) -> ProductionRuntime:
    state = DurableStateStore(config.database_path)
    queue = DurableWorkQueue(config.database_path)
    registry = registry or ActionRegistry()
    governor = RecoveryGovernor(registry, state)
    engine = governor.engine()
    worker = DurableContinuationWorker(queue, engine, config.worker_id)
    supervisor = AutonomousSupervisor(worker)
    ingress = EventIngress(queue)
    app = AutonomyWebhookApplication(ingress, config.github_webhook_secret, config.runtime_token)
    service = AutonomyService(app, supervisor, config.host, config.port)
    github = GitHubControl(
        config.github_token,
        config.repository,
        policy=GitHubWritePolicy(
            allow_branch_create=config.allow_branch_create,
            allow_merge=config.allow_merge,
            allow_comment=config.allow_comment,
        ),
        opener=github_opener,
    )
    return ProductionRuntime(config, state, queue, github, registry, governor, service)
