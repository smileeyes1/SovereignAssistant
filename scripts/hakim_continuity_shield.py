#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/HAKIM_CONTINUITY_SHIELD.json"
ACTIVE_STATE_PATH = ROOT / "governance/HAKIM_ACTIVE_STATE.json"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


@dataclass(frozen=True)
class Violation:
    code: str
    target: str
    detail: str = ""

    def render(self) -> str:
        suffix = f" :: {self.detail}" if self.detail else ""
        return f"{self.code}: {self.target}{suffix}"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def git_available() -> bool:
    return (ROOT / ".git").exists() and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def resolve_base_ref() -> str | None:
    candidate = os.getenv("HAKIM_SHIELD_BASE_REF", "").strip()
    if candidate and candidate != "0" * 40:
        if subprocess.run(
            ["git", "cat-file", "-e", f"{candidate}^{{commit}}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0:
            return candidate
    if not git_available():
        return None
    parent = git("rev-parse", "HEAD^", check=False).strip()
    return parent or None


def transition_records(policy: dict[str, Any]) -> list[dict[str, Any]]:
    registry = ROOT / str(policy["transition_registry"])
    if not registry.is_file():
        return []
    raw = load_json(registry)
    records = raw.get("transitions", [])
    return records if isinstance(records, list) else []


def valid_transition(record: dict[str, Any], root: Path = ROOT) -> bool:
    if record.get("approved") is not True:
        return False
    if record.get("mode") not in {"SUPERSEDE", "RETIRE"}:
        return False
    for key in ("target_type", "target", "rationale", "authority", "rollback"):
        if not str(record.get(key, "")).strip():
            return False
    if record.get("mode") == "SUPERSEDE" and not str(record.get("replacement", "")).strip():
        return False
    tests = record.get("evidence_tests")
    if not isinstance(tests, list) or not tests:
        return False
    return all((root / str(path)).is_file() for path in tests)


def loss_allowed(
    transitions: list[dict[str, Any]], target_type: str, target: str, root: Path = ROOT
) -> bool:
    return any(
        record.get("target_type") == target_type
        and record.get("target") == target
        and valid_transition(record, root)
        for record in transitions
    )


def public_python_symbols(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.add(node.name)
    return symbols


def python_test_symbols(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def manifest_contract(source: str) -> tuple[set[str], set[str]]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return set(), set()
    permissions = {
        node.attrib.get(f"{ANDROID_NS}name", "")
        for node in root.findall("uses-permission")
        if node.attrib.get(f"{ANDROID_NS}name")
    }
    components: set[str] = set()
    application = root.find("application")
    if application is not None:
        for kind in ("activity", "service", "receiver", "provider"):
            for node in application.findall(kind):
                name = node.attrib.get(f"{ANDROID_NS}name")
                if name:
                    components.add(f"{kind}:{name}")
    return permissions, components


def static_violations(root: Path, policy: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []

    if policy.get("fail_closed") is not True:
        violations.append(Violation("SHIELD_NOT_FAIL_CLOSED", str(POLICY_PATH)))
    if policy.get("preserve_outcomes_not_implementations") is not True:
        violations.append(Violation("OUTCOME_PRESERVATION_DISABLED", str(POLICY_PATH)))

    for rel in policy.get("required_paths", []):
        if not (root / rel).exists():
            violations.append(Violation("REQUIRED_PATH_MISSING", rel))

    capabilities = policy.get("capabilities", [])
    ids = [str(item.get("id", "")) for item in capabilities]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        violations.append(Violation("CAPABILITY_ID_INVALID", "capabilities"))

    allowed_tiers = {"P0", "P1", "P2"}
    allowed_statuses = {
        "PROTECTED_ACTIVE",
        "PROTECTED_HISTORICAL",
        "SUPERSEDED",
        "RETIRED_SECURITY_DENY",
    }
    for capability in capabilities:
        cid = str(capability.get("id", "<missing>"))
        if capability.get("tier") not in allowed_tiers:
            violations.append(Violation("CAPABILITY_TIER_INVALID", cid))
        if capability.get("status") not in allowed_statuses:
            violations.append(Violation("CAPABILITY_STATUS_INVALID", cid))
        for rel in capability.get("paths", []):
            if not (root / rel).exists():
                violations.append(Violation("CAPABILITY_PATH_MISSING", f"{cid}:{rel}"))
        tests = capability.get("tests", [])
        if capability.get("status") in {"PROTECTED_ACTIVE", "PROTECTED_HISTORICAL"} and not tests:
            violations.append(Violation("CAPABILITY_WITHOUT_TEST", cid))
        for rel in tests:
            if not (root / rel).is_file():
                violations.append(Violation("CAPABILITY_TEST_MISSING", f"{cid}:{rel}"))

    active = load_json(root / "governance/HAKIM_ACTIVE_STATE.json")
    active_success = set(active.get("proven_success", []))
    for success_id in policy.get("protected_success_ids", []):
        if success_id not in active_success:
            violations.append(Violation("PROVEN_SUCCESS_NOT_PRESERVED", success_id))

    lineage = active.get("promotion_lineage", {})
    if not isinstance(lineage, dict):
        lineage = {}
    for promotion_id in policy.get("protected_promotion_lineage_ids", []):
        if promotion_id not in lineage:
            violations.append(Violation("PROMOTION_LINEAGE_NOT_PRESERVED", promotion_id))

    android = policy.get("android_manifest", {})
    manifest_rel = str(android.get("path", ""))
    manifest_path = root / manifest_rel
    if manifest_path.is_file():
        source = manifest_path.read_text(encoding="utf-8")
        permissions, components = manifest_contract(source)
        for token in android.get("forbidden_tokens", []):
            if token in permissions:
                violations.append(Violation("FORBIDDEN_ANDROID_PERMISSION", token))
        for token in android.get("forbidden_service_tokens", []):
            if any(token in component for component in components):
                violations.append(Violation("FORBIDDEN_ANDROID_SERVICE", token))

    transitions = transition_records(policy)
    for index, record in enumerate(transitions):
        if not valid_transition(record, root):
            violations.append(Violation("INVALID_TRANSITION_RECORD", str(index)))

    return violations


def parse_diff(base_ref: str) -> list[tuple[str, str, str | None]]:
    out = git("diff", "--name-status", "--find-renames", f"{base_ref}...HEAD")
    entries: list[tuple[str, str, str | None]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            entries.append((status, parts[1], parts[2]))
        elif len(parts) >= 2:
            entries.append((status, parts[1], None))
    return entries


def git_show(base_ref: str, rel: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{rel}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def state_regressions(
    base: dict[str, Any],
    current: dict[str, Any],
    transitions: list[dict[str, Any]],
    root: Path = ROOT,
) -> list[Violation]:
    violations: list[Violation] = []

    base_success = set(base.get("proven_success", []))
    current_success = set(current.get("proven_success", []))
    for lost in sorted(base_success - current_success):
        if not loss_allowed(transitions, "success", lost, root):
            violations.append(Violation("PROVEN_SUCCESS_REMOVED", lost))

    base_lineage = base.get("promotion_lineage", {})
    current_lineage = current.get("promotion_lineage", {})
    if isinstance(base_lineage, dict) and isinstance(current_lineage, dict):
        for key, value in base_lineage.items():
            if key not in current_lineage:
                if not loss_allowed(transitions, "promotion_lineage", key, root):
                    violations.append(Violation("PROMOTION_LINEAGE_REMOVED", key))
            elif current_lineage[key] != value:
                target = f"{key}:{value}"
                if not loss_allowed(transitions, "promotion_lineage", target, root):
                    violations.append(
                        Violation("PROMOTION_LINEAGE_REWRITTEN", key, f"{value} -> {current_lineage[key]}")
                    )

    base_evidence = base.get("promotion_evidence", {})
    current_evidence = current.get("promotion_evidence", {})
    if isinstance(base_evidence, dict) and isinstance(current_evidence, dict):
        for key, value in base_evidence.items():
            if value == "PASS" and current_evidence.get(key) != "PASS":
                if not loss_allowed(transitions, "evidence", key, root):
                    violations.append(
                        Violation("PASS_EVIDENCE_DEGRADED", key, f"PASS -> {current_evidence.get(key)!r}")
                    )
    return violations


def diff_violations(root: Path, policy: dict[str, Any], base_ref: str) -> list[Violation]:
    violations: list[Violation] = []
    transitions = transition_records(policy)
    prefixes = tuple(str(x) for x in policy.get("protected_delete_prefixes", []))
    api_surfaces = set(str(x) for x in policy.get("api_surface_files", []))
    changed: dict[str, str] = {}

    try:
        entries = parse_diff(base_ref)
    except RuntimeError as exc:
        return [Violation("BASE_DIFF_UNAVAILABLE", base_ref, str(exc))]

    for status, old, new in entries:
        effective = new or old
        changed[effective] = status
        removal = status.startswith("D") or status.startswith("R")
        if removal and old.startswith(prefixes):
            if not loss_allowed(transitions, "path", old, root):
                violations.append(Violation("PROTECTED_PATH_REMOVED_OR_RENAMED", old, status))

    for rel in api_surfaces:
        if rel not in changed:
            continue
        before = git_show(base_ref, rel)
        path = root / rel
        if before is None or not path.is_file():
            continue
        after = path.read_text(encoding="utf-8")
        removed = public_python_symbols(before) - public_python_symbols(after)
        for symbol in sorted(removed):
            target = f"{rel}#{symbol}"
            if not loss_allowed(transitions, "symbol", target, root):
                violations.append(Violation("PUBLIC_SYMBOL_REMOVED", target))

    for rel, status in changed.items():
        if not rel.startswith("tests/") or not rel.endswith(".py") or status.startswith("A"):
            continue
        before = git_show(base_ref, rel)
        path = root / rel
        if before is None or not path.is_file():
            continue
        after = path.read_text(encoding="utf-8")
        removed = python_test_symbols(before) - python_test_symbols(after)
        for symbol in sorted(removed):
            target = f"{rel}#{symbol}"
            if not loss_allowed(transitions, "test", target, root):
                violations.append(Violation("TEST_CONTRACT_REMOVED", target))

    active_rel = "governance/HAKIM_ACTIVE_STATE.json"
    before_state_raw = git_show(base_ref, active_rel)
    if before_state_raw is not None and (root / active_rel).is_file():
        try:
            before_state = json.loads(before_state_raw)
            current_state = load_json(root / active_rel)
            violations.extend(state_regressions(before_state, current_state, transitions, root))
        except json.JSONDecodeError as exc:
            violations.append(Violation("ACTIVE_STATE_PARSE_ERROR", active_rel, str(exc)))

    manifest_rel = str(policy.get("android_manifest", {}).get("path", ""))
    if manifest_rel in changed and (root / manifest_rel).is_file():
        before_manifest = git_show(base_ref, manifest_rel)
        if before_manifest is not None:
            after_manifest = (root / manifest_rel).read_text(encoding="utf-8")
            before_permissions, before_components = manifest_contract(before_manifest)
            after_permissions, after_components = manifest_contract(after_manifest)
            for item in sorted(before_permissions - after_permissions):
                if not loss_allowed(transitions, "manifest_permission", item, root):
                    violations.append(Violation("ANDROID_PERMISSION_REMOVED", item))
            for item in sorted(before_components - after_components):
                if not loss_allowed(transitions, "manifest_component", item, root):
                    violations.append(Violation("ANDROID_COMPONENT_REMOVED", item))

    return violations


def run(root: Path = ROOT, base_ref: str | None = None) -> list[Violation]:
    policy = load_json(root / "governance/HAKIM_CONTINUITY_SHIELD.json")
    violations = static_violations(root, policy)
    if git_available():
        base = base_ref if base_ref is not None else resolve_base_ref()
        if base:
            violations.extend(diff_violations(root, policy, base))
    return violations


def main() -> int:
    violations = run()
    if violations:
        print("HAKIM_CONTINUITY_SHIELD=FAIL")
        for item in violations:
            print(f"- {item.render()}")
        return 1
    print("HAKIM_CONTINUITY_SHIELD=PASS")
    print("protected outcomes, evidence, tests, public surfaces and Android contracts preserved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
