"""Bounded sovereign system factory for Hakim."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Callable, Mapping

from .mission_autonomy import CandidateScore, ImprovementSandbox
from .mission_kernel import AuthorityLevel, MissionAction, MissionKernel, OperationalEnvelope

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,40}$")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class SystemSpec:
    name: str
    template: str
    capability: str
    risk: int
    reversible: bool
    authority: AuthorityLevel
    evidence: tuple[str, ...]
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class SystemGap:
    gap_id: str
    need: str
    capability: str
    risk: int
    reversible: bool
    authority: AuthorityLevel
    evidence: tuple[str, ...]
    context: Mapping[str, object]


@dataclass(frozen=True)
class FactoryPolicy:
    owned_roots: tuple[Path, ...]
    allowed_templates: frozenset[str] = frozenset({"file_freshness", "local_http_probe", "service_presence"})
    allowed_capabilities: frozenset[str] = frozenset({"system-factory"})
    max_risk: int = 2
    require_reversible_above: int = 1
    min_evidence: int = 1

    def kernel(self) -> MissionKernel:
        return MissionKernel(OperationalEnvelope(
            self.allowed_capabilities,
            max_risk=self.max_risk,
            require_reversible_above=self.require_reversible_above,
            min_evidence=self.min_evidence,
        ))

    def digest(self) -> str:
        payload = {
            "owned_roots": [str(Path(p).resolve()) for p in self.owned_roots],
            "allowed_templates": sorted(self.allowed_templates),
            "allowed_capabilities": sorted(self.allowed_capabilities),
            "max_risk": self.max_risk,
            "require_reversible_above": self.require_reversible_above,
            "min_evidence": self.min_evidence,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BuiltSystem:
    spec: SystemSpec
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class PromotionResult:
    promoted: bool
    selected: str
    reason: str
    manifest: Mapping[str, object] | None = None


RuntimeProbe = Callable[[BuiltSystem], bool]


class BoundedSystemFactory:
    def __init__(self, root: Path, policy: FactoryPolicy, *, kernel: MissionKernel | None = None, sandbox: ImprovementSandbox | None = None):
        self.root = Path(root)
        self.policy = policy
        self.kernel = kernel or policy.kernel()
        self.sandbox = sandbox or ImprovementSandbox()
        self.root.mkdir(parents=True, exist_ok=True)

    def _authorized(self, spec: SystemSpec, *, human_approved: bool) -> tuple[bool, str]:
        action = MissionAction(spec.name, spec.capability, spec.risk, spec.reversible, spec.authority, spec.evidence)
        decision = self.kernel.evaluate(action, human_approved=human_approved)
        return decision.allowed, decision.reason

    def _owned_path(self, raw: object) -> str | None:
        try:
            target = Path(str(raw)).expanduser().resolve()
        except Exception:
            return None
        for root in self.policy.owned_roots:
            owned = Path(root).expanduser().resolve()
            if target == owned or owned in target.parents:
                return str(target)
        return None

    def _normalized_parameters(self, spec: SystemSpec) -> tuple[bool, str, dict[str, object] | None]:
        params = dict(spec.parameters)
        if spec.template == "file_freshness":
            if set(params) != {"path", "max_age_seconds"}:
                return False, "file_freshness parameters must be exact", None
            path = self._owned_path(params["path"])
            try:
                age = int(params["max_age_seconds"])
            except (TypeError, ValueError):
                return False, "invalid max_age_seconds", None
            if path is None or not 10 <= age <= 86400:
                return False, "path outside owned roots or age outside policy", None
            return True, "ok", {"path": path, "max_age_seconds": age}
        if spec.template == "local_http_probe":
            if set(params) != {"url", "expected"}:
                return False, "local_http_probe parameters must be exact", None
            url = str(params["url"])
            expected = str(params["expected"])
            match = re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):([0-9]{4,5})/[A-Za-z0-9_./?=&%+-]*", url)
            if match is None or not 1024 <= int(match.group(1)) <= 65535 or len(expected) > 256:
                return False, "only bounded localhost HTTP probes are allowed", None
            return True, "ok", {"url": url, "expected": expected}
        if spec.template == "service_presence":
            if set(params) != {"service"}:
                return False, "service_presence parameters must be exact", None
            service = str(params["service"])
            if _SERVICE_RE.fullmatch(service) is None:
                return False, "invalid service name", None
            return True, "ok", {"service": service}
        return False, "template has no trusted renderer", None

    def plan_gap(self, gap: SystemGap) -> SystemSpec:
        context = dict(gap.context)
        name = str(context.pop("suggested_name", gap.gap_id))
        name = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_")
        if _NAME_RE.fullmatch(name or "") is None:
            raise ValueError("gap cannot produce a valid system name")
        if "path" in context:
            params = {"path": context.get("path"), "max_age_seconds": context.get("max_age_seconds", 120)}
            template = "file_freshness"
        elif "url" in context:
            params = {"url": context.get("url"), "expected": context.get("expected", "")}
            template = "local_http_probe"
        elif "service" in context:
            params = {"service": context.get("service")}
            template = "service_presence"
        else:
            raise ValueError("gap has no trusted deterministic template")
        spec = SystemSpec(name, template, gap.capability, gap.risk, gap.reversible, gap.authority, gap.evidence, params)
        ok, reason = self.validate(spec)
        if not ok:
            raise PermissionError(reason)
        return spec

    def validate(self, spec: SystemSpec, *, human_approved: bool = False) -> tuple[bool, str]:
        if _NAME_RE.fullmatch(spec.name) is None:
            return False, "invalid system name"
        if spec.template not in self.policy.allowed_templates:
            return False, "template outside factory policy"
        if spec.capability not in self.policy.allowed_capabilities:
            return False, "capability outside factory policy"
        ok, reason = self._authorized(spec, human_approved=human_approved)
        if not ok:
            return False, reason
        ok, reason, _ = self._normalized_parameters(spec)
        return ok, reason

    def build(self, spec: SystemSpec, *, human_approved: bool = False) -> BuiltSystem:
        ok, reason = self.validate(spec, human_approved=human_approved)
        if not ok:
            raise PermissionError(reason)
        _, _, params = self._normalized_parameters(spec)
        assert params is not None
        payload_obj = {
            "schema": "hakim.system.v1",
            "name": spec.name,
            "template": spec.template,
            "capability": spec.capability,
            "risk": spec.risk,
            "reversible": spec.reversible,
            "authority": int(spec.authority),
            "parameters": params,
        }
        payload = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return BuiltSystem(spec, payload, sha256(payload).hexdigest())

    def _module_dir(self, name: str) -> Path:
        return self.root / name

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    @staticmethod
    def _spec_bytes(spec: SystemSpec) -> bytes:
        data = asdict(spec)
        data["authority"] = int(spec.authority)
        data["evidence"] = list(spec.evidence)
        data["parameters"] = dict(spec.parameters)
        return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2).encode()

    def current(self, name: str) -> BuiltSystem | None:
        module = self._module_dir(name)
        payload_path = module / "current.json"
        spec_path = module / "current.spec.json"
        if not payload_path.exists() or not spec_path.exists():
            return None
        data = json.loads(spec_path.read_text())
        spec = SystemSpec(
            data["name"], data["template"], data["capability"], int(data["risk"]), bool(data["reversible"]),
            AuthorityLevel(int(data["authority"])), tuple(data.get("evidence", ())), dict(data["parameters"]),
        )
        payload = payload_path.read_bytes()
        return BuiltSystem(spec, payload, sha256(payload).hexdigest())

    def _promote_files(self, built: BuiltSystem, manifest: Mapping[str, object]) -> None:
        module = self._module_dir(built.spec.name)
        module.mkdir(parents=True, exist_ok=True)
        current = module / "current.json"
        current_spec = module / "current.spec.json"
        manifest_path = module / "manifest.json"
        if current.exists():
            shutil.copy2(current, module / "previous.json")
        if current_spec.exists():
            shutil.copy2(current_spec, module / "previous.spec.json")
        if manifest_path.exists():
            shutil.copy2(manifest_path, module / "previous.manifest.json")
        self._write_atomic(current, built.payload)
        self._write_atomic(current_spec, self._spec_bytes(built.spec))
        self._write_atomic(manifest_path, json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2).encode())

    def qualify_and_promote(self, built: BuiltSystem, *, challenger: CandidateScore, champion: CandidateScore | None,
                            probe: RuntimeProbe, human_approved: bool = False) -> PromotionResult:
        ok, reason = self.validate(built.spec, human_approved=human_approved)
        if not ok:
            return PromotionResult(False, champion.name if champion else "", reason)
        if champion is None:
            champion = CandidateScore("none", -1.0, challenger.safety, True)
        decision = self.sandbox.choose(champion, challenger)
        if not decision.promote:
            return PromotionResult(False, decision.selected, decision.reason)
        canary = self.sandbox.canary(decision, lambda: probe(built))
        if not canary.promote:
            return PromotionResult(False, canary.selected, canary.reason)
        manifest = {
            "schema": "hakim.system.manifest.v1",
            "name": built.spec.name,
            "template": built.spec.template,
            "artifact_sha256": built.sha256,
            "policy_sha256": self.policy.digest(),
            "canary": "passed",
            "challenger": {
                "name": challenger.name,
                "quality": challenger.quality,
                "safety": challenger.safety,
                "regression_passed": challenger.regression_passed,
            },
        }
        self._promote_files(built, manifest)
        return PromotionResult(True, built.spec.name, "challenger promoted after canary", manifest)

    def rollback(self, name: str, *, failing_probe: RuntimeProbe) -> bool:
        current = self.current(name)
        if current is None or failing_probe(current):
            return False
        module = self._module_dir(name)
        previous = module / "previous.json"
        previous_spec = module / "previous.spec.json"
        previous_manifest = module / "previous.manifest.json"
        if not previous.exists() or not previous_spec.exists():
            return False
        shutil.copy2(module / "current.json", module / "failed.json")
        self._write_atomic(module / "current.json", previous.read_bytes())
        self._write_atomic(module / "current.spec.json", previous_spec.read_bytes())
        if previous_manifest.exists():
            manifest = json.loads(previous_manifest.read_text())
            manifest["rollback"] = {"performed": True, "failed_artifact_sha256": current.sha256}
            self._write_atomic(module / "manifest.json", json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2).encode())
        return True
