"""Replaceable coding-provider layer with validation, failover and cost governance."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Callable, Protocol
from urllib.request import Request, urlopen

from .capability_registry import CapabilityRegistry
from .cost_policy import COST_RANK, CostPolicy, CostTier


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
    cost_tier: CostTier | str

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


def _tier(provider: CodingProvider) -> CostTier:
    raw = getattr(provider, "cost_tier", CostTier.UNKNOWN)
    if isinstance(raw, CostTier):
        return raw
    try:
        return CostTier(str(raw).strip().lower())
    except ValueError:
        return CostTier.UNKNOWN


class CodingProviderPool:
    """Fail over across providers while enforcing free-first resource policy."""

    def __init__(
        self,
        providers: list[CodingProvider],
        capability_registry: CapabilityRegistry | None = None,
        *,
        cost_policy: CostPolicy | None = None,
    ):
        if not providers:
            raise ValueError("at least one coding provider is required")
        # Stable sort: keep caller order inside each cost tier.
        self.providers = sorted(providers, key=lambda p: COST_RANK[_tier(p)])
        self.capability_registry = capability_registry
        self.cost_policy = cost_policy or CostPolicy()
        self.failures: list[tuple[str, str]] = []
        self.paid_calls_used = 0

    def propose_patch(self, request: PatchRequest) -> PatchPlan:
        self.failures.clear()
        attempted = 0
        for provider in self.providers:
            tier = _tier(provider)
            if tier is CostTier.PAID and not self.cost_policy.admits(tier, paid_calls_used=self.paid_calls_used):
                self.failures.append((provider.name, "paid provider blocked by free-first policy/budget"))
                continue
            if self.capability_registry is not None and not self.capability_registry.is_healthy(provider.name):
                self.failures.append((provider.name, "unhealthy capability excluded"))
                continue
            attempted += 1
            if tier is CostTier.PAID:
                # Count attempts, not only successes: failed paid requests may still consume quota/cost.
                self.paid_calls_used += 1
            try:
                bounded = PatchRequest(
                    request.objective,
                    request.failure_log[-self.cost_policy.max_failure_log_chars :],
                    request.files,
                )
                plan = validate_patch(provider.propose_patch(bounded))
                if self.capability_registry is not None:
                    self.capability_registry.record_success(provider.name)
                return plan
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.failures.append((provider.name, error))
                if self.capability_registry is not None:
                    self.capability_registry.record_failure(provider.name, error)
        if attempted == 0:
            reasons = "; ".join(f"{n}={e}" for n, e in self.failures)
            raise RuntimeError("no admitted healthy coding providers available" + (": " + reasons if reasons else ""))
        raise RuntimeError("all coding providers failed: " + "; ".join(f"{n}={e}" for n, e in self.failures))

    def usage_snapshot(self) -> dict[str, object]:
        return {
            "cost_mode": self.cost_policy.mode,
            "paid_calls_used": self.paid_calls_used,
            "paid_call_budget": self.cost_policy.max_paid_calls,
            "provider_order": [p.name for p in self.providers],
            "provider_tiers": {p.name: _tier(p).value for p in self.providers},
        }


class OpenAIResponsesCodingProvider:
    """Optional paid reference adapter. Ω APEX does not depend on this provider."""

    cost_tier = CostTier.PAID

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
            "failure_log": request.failure_log,
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
        return _plan_from_parsed(self.name, parsed)


class OpenAICompatibleChatCodingProvider:
    """OpenAI-compatible chat adapter for local or zero-cost endpoints.

    This intentionally uses the widely supported /chat/completions shape so it can
    connect to local runtimes (for example, an OpenAI-compatible local server) or
    a user-selected free-tier provider without coupling Ω APEX to one vendor.
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str = "",
        cost_tier: CostTier = CostTier.FREE,
        max_output_tokens: int = 3_072,
        opener: Callable[..., object] | None = None,
        name: str = "openai-compatible-free",
    ):
        if not model.strip() or not base_url.strip():
            raise ValueError("model and base_url are required")
        if cost_tier is CostTier.PAID:
            raise ValueError("paid endpoints must use an explicitly paid adapter/policy")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.cost_tier = cost_tier
        self.max_output_tokens = max_output_tokens
        self._opener = opener or urlopen
        self.name = name

    @staticmethod
    def _json_text(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("provider response does not contain a JSON object")
        return cleaned[start : end + 1]

    def propose_patch(self, request: PatchRequest) -> PatchPlan:
        context = {
            "objective": request.objective,
            "failure_log": request.failure_log,
            "files": request.files,
        }
        instruction = (
            "You are a repository repair worker. Return ONLY one JSON object with keys summary and files. "
            "files must be an array of {path, content} objects containing complete replacement text only for files that must change. "
            "Make the smallest safe patch, preserve working behavior, do not invent paths, and do not use Markdown fences."
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "max_tokens": self.max_output_tokens,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "omega-apex-free-first",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = Request(f"{self.base_url}/chat/completions", data=body, method="POST", headers=headers)
        response = self._opener(req, timeout=120)
        data = json.loads(response.read().decode("utf-8"))
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("provider response has no choices")
        message = choices[0].get("message", {})
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("provider response has no message content")
        parsed = json.loads(self._json_text(message["content"]))
        return _plan_from_parsed(self.name, parsed)


def _plan_from_parsed(provider_name: str, parsed: object) -> PatchPlan:
    if not isinstance(parsed, dict):
        raise ValueError("provider output must be an object")
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
    return validate_patch(PatchPlan(provider_name, str(parsed.get("summary", "")), changes))
