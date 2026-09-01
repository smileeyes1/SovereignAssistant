"""Ω Forge R2: deterministic intent-to-app vertical slice.

R2 proves the product flow without depending on any AI vendor: compile a human
intent into a small app plan, let a replaceable coding worker materialize files,
verify the result, repair when needed, checkpoint state, and expose a preview.
Model-backed workers can be added later behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol

from .r1 import ProjectStore, PreviewHandle, PreviewServer


@dataclass(frozen=True)
class AppPlan:
    project_id: str
    title: str
    intent: str
    acceptance_markers: tuple[str, ...]


class GoalCompiler:
    """Turns a minimal end-user intent into an executable internal contract."""

    def compile(self, project_id: str, intent: str) -> AppPlan:
        clean = " ".join(intent.split())
        if not project_id.strip():
            raise ValueError("project_id is required")
        if not clean:
            raise ValueError("intent is required")
        title = clean[:72]
        return AppPlan(project_id=project_id, title=title, intent=clean, acceptance_markers=(clean,))


class CodingWorker(Protocol):
    name: str
    def build(self, plan: AppPlan) -> dict[str, str]: ...
    def repair(self, plan: AppPlan, files: dict[str, str], failures: tuple[str, ...]) -> dict[str, str]: ...


@dataclass
class TemplateCodingWorker:
    name: str = "template"

    def build(self, plan: AppPlan) -> dict[str, str]:
        escaped = (plan.intent.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
        html = ("<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'>" f"<title>{escaped}</title><main><h1>{escaped}</h1>" "<p>تم إنشاء هذا المشروع عبر Ω Forge.</p></main></html>")
        return {"index.html": html}

    def repair(self, plan: AppPlan, files: dict[str, str], failures: tuple[str, ...]) -> dict[str, str]:
        return self.build(plan)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    failures: tuple[str, ...] = ()


class AppVerifier:
    def verify(self, plan: AppPlan, files: dict[str, str]) -> VerificationResult:
        failures: list[str] = []
        index = files.get("index.html", "")
        if not index:
            failures.append("index.html is missing")
        for marker in plan.acceptance_markers:
            if marker not in index:
                failures.append(f"acceptance marker missing: {marker}")
        return VerificationResult(not failures, tuple(failures))


@dataclass(frozen=True)
class Checkpoint:
    digest: str
    files: dict[str, str]


@dataclass
class CheckpointStore:
    checkpoints: dict[str, list[Checkpoint]] = field(default_factory=dict)

    def save(self, project_id: str, files: dict[str, str]) -> Checkpoint:
        canonical = "\n".join(f"{k}\0{files[k]}" for k in sorted(files))
        checkpoint = Checkpoint(sha256(canonical.encode("utf-8")).hexdigest(), dict(files))
        self.checkpoints.setdefault(project_id, []).append(checkpoint)
        return checkpoint

    def latest(self, project_id: str) -> Checkpoint | None:
        items = self.checkpoints.get(project_id, [])
        return items[-1] if items else None


@dataclass
class BuildOutcome:
    plan: AppPlan
    verification: VerificationResult
    checkpoint: Checkpoint
    preview: PreviewHandle
    repair_attempts: int


@dataclass
class IntentToAppEngine:
    store: ProjectStore
    worker: CodingWorker = field(default_factory=TemplateCodingWorker)
    compiler: GoalCompiler = field(default_factory=GoalCompiler)
    verifier: AppVerifier = field(default_factory=AppVerifier)
    checkpoints: CheckpointStore = field(default_factory=CheckpointStore)
    preview_server: PreviewServer = field(default_factory=PreviewServer)
    max_repairs: int = 2

    def build(self, project_id: str, intent: str) -> BuildOutcome:
        plan = self.compiler.compile(project_id, intent)
        files = self.worker.build(plan)
        attempts = 0
        verification = self.verifier.verify(plan, files)
        while not verification.passed and attempts < self.max_repairs:
            attempts += 1
            files = self.worker.repair(plan, files, verification.failures)
            verification = self.verifier.verify(plan, files)
        if not verification.passed:
            raise RuntimeError("intent-to-app verification failed: " + "; ".join(verification.failures))
        for rel, content in files.items():
            self.store.write_text(project_id, rel, content)
        checkpoint = self.checkpoints.save(project_id, self.store.snapshot(project_id))
        preview = self.preview_server.start(self.store.project_path(project_id))
        return BuildOutcome(plan, verification, checkpoint, preview, attempts)
