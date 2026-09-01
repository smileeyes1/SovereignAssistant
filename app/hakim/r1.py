from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import subprocess, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


@dataclass
class ProjectStore:
    root: Path

    def __post_init__(self):
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def project_path(self, project_id: str) -> Path:
        if not project_id.strip():
            raise ValueError("project_id is required")
        candidate = (self.root / project_id).resolve()
        if self.root not in candidate.parents:
            raise ValueError("project_id escapes storage root")
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def write_text(self, project_id: str, rel: str, content: str) -> Path:
        base = self.project_path(project_id)
        target = (base / rel).resolve()
        if base not in target.parents and target != base:
            raise ValueError("path escapes project root")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def snapshot(self, project_id: str) -> dict[str, str]:
        base = self.project_path(project_id)
        out = {}
        for p in base.rglob("*"):
            if p.is_file():
                out[str(p.relative_to(base))] = p.read_text(encoding="utf-8", errors="replace")
        return out


@dataclass
class ExecutionResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class LocalRuntime:
    store: ProjectStore
    timeout_seconds: int = 30
    logs: list[dict] = field(default_factory=list)

    def run(self, project_id: str, command: list[str]) -> ExecutionResult:
        if not command:
            raise ValueError("command is required")
        cwd = self.store.project_path(project_id)
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=self.timeout_seconds)
        result = ExecutionResult(command, proc.returncode, proc.stdout, proc.stderr)
        self.logs.append({"project_id": project_id, "command": command, "returncode": proc.returncode,
                          "stdout": proc.stdout, "stderr": proc.stderr})
        return result


@dataclass
class PreviewHandle:
    url: str
    stop: Callable[[], None]


class PreviewServer:
    def start(self, root: Path, host: str = "127.0.0.1", port: int = 0) -> PreviewHandle:
        root = Path(root).resolve()
        handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(root), **kw)
        server = ThreadingHTTPServer((host, port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        actual = server.server_address[1]
        return PreviewHandle(f"http://{host}:{actual}", lambda: (server.shutdown(), server.server_close()))


@dataclass(frozen=True)
class ContinuationStep:
    name: str
    safe: bool
    reversible: bool
    ready: bool = True


class ContinuationEngine:
    """Selects the highest-value safe next step without user micromanagement."""

    def choose(self, steps: list[ContinuationStep]) -> ContinuationStep | None:
        for step in steps:
            if step.ready and step.safe and step.reversible:
                return step
        return None
