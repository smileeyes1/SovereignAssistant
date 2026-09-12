import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/hakim_continuity_shield.py"
SPEC = importlib.util.spec_from_file_location("hakim_continuity_shield", MODULE_PATH)
assert SPEC and SPEC.loader
shield = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shield)


def policy():
    return json.loads((ROOT / "governance/HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))


def test_current_tree_satisfies_static_continuity_contract():
    assert shield.static_violations(ROOT, policy()) == []


def test_proven_success_removal_fails_closed():
    base = {"proven_success": ["alpha", "beta"], "promotion_lineage": {}, "promotion_evidence": {}}
    current = {"proven_success": ["alpha"], "promotion_lineage": {}, "promotion_evidence": {}}
    violations = shield.state_regressions(base, current, [], ROOT)
    assert any(v.code == "PROVEN_SUCCESS_REMOVED" and v.target == "beta" for v in violations)


def test_pass_evidence_cannot_silently_degrade():
    base = {"proven_success": [], "promotion_lineage": {}, "promotion_evidence": {"gate": "PASS"}}
    current = {"proven_success": [], "promotion_lineage": {}, "promotion_evidence": {"gate": "PENDING"}}
    violations = shield.state_regressions(base, current, [], ROOT)
    assert any(v.code == "PASS_EVIDENCE_DEGRADED" and v.target == "gate" for v in violations)


def test_promotion_lineage_cannot_be_removed_or_rewritten():
    base = {
        "proven_success": [],
        "promotion_lineage": {"alpha": "a" * 40, "beta": "b" * 40},
        "promotion_evidence": {},
    }
    current = {
        "proven_success": [],
        "promotion_lineage": {"alpha": "c" * 40},
        "promotion_evidence": {},
    }
    violations = shield.state_regressions(base, current, [], ROOT)
    codes = {(v.code, v.target) for v in violations}
    assert ("PROMOTION_LINEAGE_REWRITTEN", "alpha") in codes
    assert ("PROMOTION_LINEAGE_REMOVED", "beta") in codes


def test_explicit_approved_supersession_allows_intentional_evolution(tmp_path):
    evidence = tmp_path / "proof.py"
    evidence.write_text("def test_replacement():\n    assert True\n", encoding="utf-8")
    transition = {
        "target_type": "success",
        "target": "old_capability",
        "mode": "SUPERSEDE",
        "replacement": "safer_capability",
        "rationale": "أقل صلاحية مع حفظ الغاية",
        "authority": "latest_explicit_user_and_governance",
        "rollback": "restore_last_verified_baseline",
        "evidence_tests": ["proof.py"],
        "approved": True,
    }
    base = {"proven_success": ["old_capability"], "promotion_lineage": {}, "promotion_evidence": {}}
    current = {"proven_success": [], "promotion_lineage": {}, "promotion_evidence": {}}
    assert shield.state_regressions(base, current, [transition], tmp_path) == []


def test_public_python_surface_loss_is_detectable():
    before = "class PublicClass:\n    pass\n\ndef public_fn():\n    return 1\n\ndef _private():\n    return 2\n"
    after = "def public_fn():\n    return 1\n"
    removed = shield.public_python_symbols(before) - shield.public_python_symbols(after)
    assert removed == {"PublicClass"}


def test_test_contract_loss_is_detectable():
    before = "def test_alpha():\n    pass\n\ndef test_beta():\n    pass\n"
    after = "def test_alpha():\n    pass\n"
    removed = shield.python_test_symbols(before) - shield.python_test_symbols(after)
    assert removed == {"test_beta"}


def test_android_manifest_parser_ignores_comments_but_sees_registered_services():
    comment_only = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><!-- AccessibilityService --></application></manifest>'''
    _, components = shield.manifest_contract(comment_only)
    assert not any("AccessibilityService" in item for item in components)

    registered = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><service android:name=".HakimAccessibilityService" /></application></manifest>'''
    _, components = shield.manifest_contract(registered)
    assert "service:.HakimAccessibilityService" in components


def test_transition_records_fail_closed_without_proof(tmp_path):
    invalid = {
        "target_type": "path",
        "target": "app/hakim/core.py",
        "mode": "RETIRE",
        "rationale": "reason",
        "authority": "authority",
        "rollback": "rollback",
        "evidence_tests": ["missing_test.py"],
        "approved": True,
    }
    assert shield.valid_transition(invalid, tmp_path) is False


def test_governance_workflow_runs_shield_before_regression_suite():
    workflow = (ROOT / ".github/workflows/governance.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    shield_pos = workflow.index("python scripts/hakim_continuity_shield.py")
    pytest_pos = workflow.index("python -m pytest -q")
    assert shield_pos < pytest_pos
    assert "HAKIM_SHIELD_BASE_REF" in workflow
