"""Ω Forge: sovereign, provider-agnostic development workspace control plane.

This module deliberately owns workspace lifecycle semantics while delegating the
actual sandbox implementation to replaceable runtime backends. Docker, gVisor,
Firecracker, Kubernetes, local processes, or future runtimes can be adapters;
they are never the product identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from uuid import uuid4


class WorkspaceStatus(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkspaceSpec:
    """Portable workspace intent, independent of any cloud or runtime vendor."""

    name: str
    image: str = "python:3.13-slim"
    cpu: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 4096
    repository: str | None = None
    devcontainer_path: str | None = None
    allow_network: bool = True
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("workspace name is required")
        if self.cpu <= 0:
            raise ValueError("cpu must be positive")
        if self.memory_mb < 128:
            raise ValueError("memory_mb is below the supported minimum")
        if self.disk_mb < 256:
            raise ValueError("disk_mb is below the supported minimum")


@dataclass
class Workspace:
    id: str
    spec: WorkspaceSpec
    backend: str
    status: WorkspaceStatus = WorkspaceStatus.CREATED
    endpoint: str | None = None
    runtime_id: str | None = None
    failure_reason: str | None = None


class RuntimeBackend(Protocol):
    """Replaceable sandbox/runtime adapter contract."""

    name: str

    def healthy(self) -> bool: ...

    def create(self, workspace_id: str, spec: WorkspaceSpec) -> str: ...

    def start(self, runtime_id: str) -> str | None: ...

    def stop(self, runtime_id: str) -> None: ...

    def destroy(self, runtime_id: str) -> None: ...


@dataclass
class WorkspaceControlPlane:
    """Owns workspace state, routing and lifecycle without vendor lock-in."""

    backends: dict[str, RuntimeBackend] = field(default_factory=dict)
    workspaces: dict[str, Workspace] = field(default_factory=dict)

    def register_backend(self, backend: RuntimeBackend) -> None:
        if not backend.name.strip():
            raise ValueError("backend name is required")
        self.backends[backend.name] = backend

    def create_workspace(
        self,
        spec: WorkspaceSpec,
        preferred_backends: tuple[str, ...] = (),
    ) -> Workspace:
        backend = self._select_backend(preferred_backends)
        workspace_id = str(uuid4())
        runtime_id = backend.create(workspace_id, spec)
        workspace = Workspace(
            id=workspace_id,
            spec=spec,
            backend=backend.name,
            runtime_id=runtime_id,
        )
        self.workspaces[workspace_id] = workspace
        return workspace

    def start_workspace(self, workspace_id: str) -> Workspace:
        workspace = self._get(workspace_id)
        if workspace.status is WorkspaceStatus.RUNNING:
            return workspace
        if workspace.runtime_id is None:
            raise RuntimeError("workspace has no runtime")

        backend = self.backends[workspace.backend]
        workspace.status = WorkspaceStatus.STARTING
        try:
            workspace.endpoint = backend.start(workspace.runtime_id)
            workspace.status = WorkspaceStatus.RUNNING
            workspace.failure_reason = None
        except Exception as exc:
            workspace.status = WorkspaceStatus.FAILED
            workspace.failure_reason = str(exc)
            raise
        return workspace

    def stop_workspace(self, workspace_id: str) -> Workspace:
        workspace = self._get(workspace_id)
        if workspace.status in {WorkspaceStatus.CREATED, WorkspaceStatus.STOPPED}:
            workspace.status = WorkspaceStatus.STOPPED
            return workspace
        if workspace.runtime_id is None:
            raise RuntimeError("workspace has no runtime")

        workspace.status = WorkspaceStatus.STOPPING
        backend = self.backends[workspace.backend]
        try:
            backend.stop(workspace.runtime_id)
            workspace.status = WorkspaceStatus.STOPPED
            workspace.endpoint = None
            workspace.failure_reason = None
        except Exception as exc:
            workspace.status = WorkspaceStatus.FAILED
            workspace.failure_reason = str(exc)
            raise
        return workspace

    def destroy_workspace(self, workspace_id: str) -> None:
        workspace = self._get(workspace_id)
        if workspace.runtime_id is not None:
            self.backends[workspace.backend].destroy(workspace.runtime_id)
        del self.workspaces[workspace_id]

    def _select_backend(self, preferred_backends: tuple[str, ...]) -> RuntimeBackend:
        ordered = list(preferred_backends) + [
            name for name in self.backends if name not in preferred_backends
        ]
        for name in ordered:
            backend = self.backends.get(name)
            if backend is not None and backend.healthy():
                return backend
        raise RuntimeError("no healthy Ω Forge runtime backend is available")

    def _get(self, workspace_id: str) -> Workspace:
        try:
            return self.workspaces[workspace_id]
        except KeyError as exc:
            raise KeyError(f"unknown workspace: {workspace_id}") from exc
