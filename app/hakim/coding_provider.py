"""Replaceable coding-provider layer with validation and provider failover."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Callable, Protocol
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PatchRequest:
    objective: str
    failure_log: str
    files: dict[str, str]


@dataclass(frozen=True)
class PatchPlan:
    provider: str
    summary: str
    changes: dict[str, str]


class CodingProvider(Protocol):
    name: str
    def propose_patch(self, request: PatchRequest) -> PatchPlan: ...


def validate_patch(plan: PatchPlan, *, max_files: int = 20, max_total_chars: int = 500_000) -> PatchPlan:
    if not plan.summary.strip():
        raise ValueError("patch summary is required")
    if not plan.changes:
        raise ValueError("patch must contain at least one file change")
    if len(plan.changes) > max_files:
        raise ValueError("patch changes too many files")
    total = 0
    for path, content in plan.changes.items():
        p = PurePosixPath(path)
        if not path.strip() or p.is_absolute() or ".." in p.parts or path.startswith("."):
            raise ValueError(f"unsafe patch path: {path}")
        if not isinstance(content, str):
            raise ValueError("patch content must be text")
        total += len(content)
    if total > max_total_chars:
        raise ValueError("patch is too large")
    return plan


class CodingProviderPool:
    def __init__(self, providers: list[CodingProvider]):
        if not providers:
            raise ValueError("at least one coding provider is required")
        self.providers = providers
        self.failures: list[tuple[str, str]] = []

    def propose_patch(self, request: PatchRequest) -> PatchPlan:
        self.failures.clear()
        for provider in self.providers:
            try:
                return validate_patch(provider.propose_patch(request))
            except Exception as exc:
                self.failures.append((provider.name, f"{type(exc).__name__}: {exc}"))
        raise RuntimeError("all coding providers failed: " + "; ".join(f"{n}={e}" for n, e in self.failures))


class OpenAIResponsesCodingProvider:
    """Optional reference adapter. Ω APEX does not depend on this provider."""

    def __init__(self, api_key: str, model: str, *, base_url: str = "https://api.openai.com/v1", opener: Callable[..., object] | None = None, name: str = "openai-responses"):
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model are required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._opener = opener or urlopen
        self.name = name

    @staticmethod
    def _schema() -> dict[str, object]:
        return {
            "type": "json_schema",
            "name": "omega_patch_plan",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["path", "content"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["summary", "files"],
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _output_text(response: dict[str, object]) -> str:
        output = response.get("output", [])
        if not isinstance(output, list):
            raise ValueError("provider response has no output")
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
        if not parts:
            raise ValueError("provider response has no output_text")
        return "".join(parts)

    def propose_patch(self, request: PatchRequest) -> PatchPlan:
        context = {
            "objective": request.objective,
            "failure_log": request.failure_log[-20_000:],
            "files": request.files,
        }
        prompt = (
            "You are a repository repair worker. Produce the smallest safe patch that resolves the stated failure. "
            "Return complete replacement text only for files that must change. Do not invent paths outside the repository. "
            "Preserve working behavior and minimize regression risk.\n\n" + json.dumps(context, ensure_ascii=False)
        )
        body = json.dumps(
            {
                "model": self.model,
                "input": prompt,
                "store": False,
                "text": {"format": self._schema()},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/responses",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "omega-apex",
            },
        )
        response = self._opener(req, timeout=120)
        data = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(self._output_text(data))
        files = parsed.get("files", [])
        if not isinstance(files, list):
            raise ValueError("files must be a list")
        changes: dict[str, str] = {}
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("invalid file change")
            path, content = item.get("path"), item.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                raise ValueError("invalid file path/content")
            if path in changes:
                raise ValueError(f"duplicate file path: {path}")
            changes[path] = content
        return validate_patch(PatchPlan(self.name, str(parsed.get("summary", "")), changes))
