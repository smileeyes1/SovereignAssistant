import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"
SOURCE_MAIN = "2149d6dcb60339625fb27551dcc6b670ffbc59bc"
FROZEN_PHONE_BASELINE = "a6225e4118d68871ed00c8328f072fd8bd15bfc6"


def load(name: str):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_autonomous_mutation_guard_promotion_is_source_bound_and_verified():
    promotion = load("HAKIM_AUTONOMOUS_MUTATION_GUARD_PROMOTION.json")
    assert promotion["status"] == "ACTIVE_VERIFIED"
    assert promotion["source_main"] == SOURCE_MAIN
    assert all(value == "PASS" for value in promotion["proven"].values())
    guard = promotion["guard_contract"]
    assert guard["autonomous_direct_write_to_main_or_master"] is False
    assert guard["candidate_branch_only_mutations"] is True
    assert guard["required_autonomous_merge_workflows"] == [
        "HAKIM Governance Gate",
        "HAKIM Continuity Shield",
    ]
    assert guard["required_workflow_conclusion"] == "completed_success"
    assert guard["expected_head_sha_lock"] is True
    assert guard["default_autonomous_merge_enabled"] is False


def test_autonomous_mutation_guard_is_durable_proven_success_without_field_overclaim():
    state = load("HAKIM_ACTIVE_STATE.json")
    assert state["promotion_lineage"]["autonomous_mutation_guard_v1"] == SOURCE_MAIN
    assert "autonomous_mutation_guard_v1" in state["proven_success"]
    assert state["autonomous_mutation_guard_promotion"] == "governance/HAKIM_AUTONOMOUS_MUTATION_GUARD_PROMOTION.json"
    for key in (
        "autonomous_mutation_guard_governance_main",
        "autonomous_mutation_guard_continuity_main",
        "autonomous_mutation_guard_reality_main",
        "autonomous_mutation_guard_no_direct_protected_branch_write",
        "autonomous_mutation_guard_required_merge_workflows",
    ):
        assert state["promotion_evidence"][key] == "PASS"
    assert state["last_verified_baseline"] == FROZEN_PHONE_BASELINE
    assert state["latest_observed_main"] == FROZEN_PHONE_BASELINE
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"


def test_continuity_shield_keeps_mutation_guard_as_p0_capability():
    policy = load("HAKIM_CONTINUITY_SHIELD.json")
    capability = next(item for item in policy["capabilities"] if item["id"] == "autonomous_mutation_guard")
    assert capability["tier"] == "P0"
    assert capability["status"] == "PROTECTED_ACTIVE"
    assert "app/hakim/github_control.py" in capability["paths"]
    assert "app/hakim/development_actions.py" in capability["paths"]
    assert "tests/test_github_control.py" in capability["tests"]
    assert "tests/test_development_actions.py" in capability["tests"]


def test_autonomous_continuation_retries_when_either_governing_workflow_completes_without_enabling_merge():
    workflow = (ROOT / ".github/workflows/autonomous-continuation.yml").read_text(encoding="utf-8")
    assert 'workflows: ["HAKIM Governance Gate", "HAKIM Continuity Shield"]' in workflow
    assert "OMEGA_ALLOW_MERGE: 'false'" in workflow
