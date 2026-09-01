import pytest

from app.hakim import WorkspaceControlPlane, WorkspaceSpec, WorkspaceStatus


class FakeBackend:
    def __init__(self, name="fake", healthy=True, fail_start=False):
        self.name = name
        self._healthy = healthy
        self.fail_start = fail_start
        self.created = []
        self.stopped = []
        self.destroyed = []

    def healthy(self):
        return self._healthy

    def create(self, workspace_id, spec):
        runtime_id = f"runtime:{workspace_id}"
        self.created.append((runtime_id, spec))
        return runtime_id

    def start(self, runtime_id):
        if self.fail_start:
            raise RuntimeError("start failed")
        return f"https://preview.local/{runtime_id}"

    def stop(self, runtime_id):
        self.stopped.append(runtime_id)

    def destroy(self, runtime_id):
        self.destroyed.append(runtime_id)


def test_workspace_spec_rejects_invalid_resources():
    with pytest.raises(ValueError):
        WorkspaceSpec(name="bad", memory_mb=64)


def test_control_plane_selects_healthy_fallback_backend():
    plane = WorkspaceControlPlane()
    plane.register_backend(FakeBackend(name="primary", healthy=False))
    plane.register_backend(FakeBackend(name="fallback", healthy=True))

    workspace = plane.create_workspace(
        WorkspaceSpec(name="demo"),
        preferred_backends=("primary", "fallback"),
    )

    assert workspace.backend == "fallback"
    assert workspace.status is WorkspaceStatus.CREATED


def test_start_stop_and_destroy_workspace_lifecycle():
    plane = WorkspaceControlPlane()
    backend = FakeBackend()
    plane.register_backend(backend)
    workspace = plane.create_workspace(WorkspaceSpec(name="demo"))

    started = plane.start_workspace(workspace.id)
    assert started.status is WorkspaceStatus.RUNNING
    assert started.endpoint is not None

    stopped = plane.stop_workspace(workspace.id)
    assert stopped.status is WorkspaceStatus.STOPPED
    assert stopped.endpoint is None

    plane.destroy_workspace(workspace.id)
    assert workspace.id not in plane.workspaces
    assert backend.destroyed == [workspace.runtime_id]


def test_failed_start_is_recorded_and_raised():
    plane = WorkspaceControlPlane()
    backend = FakeBackend(fail_start=True)
    plane.register_backend(backend)
    workspace = plane.create_workspace(WorkspaceSpec(name="demo"))

    with pytest.raises(RuntimeError, match="start failed"):
        plane.start_workspace(workspace.id)

    assert workspace.status is WorkspaceStatus.FAILED
    assert workspace.failure_reason == "start failed"


def test_no_healthy_runtime_fails_closed():
    plane = WorkspaceControlPlane()
    plane.register_backend(FakeBackend(name="down", healthy=False))

    with pytest.raises(RuntimeError, match="no healthy"):
        plane.create_workspace(WorkspaceSpec(name="demo"))
