import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/hakim_continuity_shield.py"
SPEC = importlib.util.spec_from_file_location("hakim_continuity_shield", MODULE_PATH)
assert SPEC and SPEC.loader
shield = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shield
SPEC.loader.exec_module(shield)


def policy():
    return json.loads((ROOT / "governance/HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))


def prepare_minimal_root(root: Path):
    governance = root / "governance"
    governance.mkdir(parents=True, exist_ok=True)
    (governance / "HAKIM_ACTIVE_STATE.json").write_text(
        json.dumps({"proven_success": [], "promotion_lineage": {}, "promotion_evidence": {}}),
        encoding="utf-8",
    )


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
    base = {"proven_success": [], "promotion_lineage": {"alpha": "a" * 40, "beta": "b" * 40}, "promotion_evidence": {}}
    current = {"proven_success": [], "promotion_lineage": {"alpha": "c" * 40}, "promotion_evidence": {}}
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
    assert shield.public_python_symbols(before) - shield.public_python_symbols(after) == {"PublicClass"}


def test_test_contract_loss_is_detectable():
    before = "def test_alpha():\n    pass\n\ndef test_beta():\n    pass\n"
    after = "def test_alpha():\n    pass\n"
    assert shield.python_test_symbols(before) - shield.python_test_symbols(after) == {"test_beta"}


def test_android_manifest_parser_ignores_comments_but_sees_registered_services():
    comment_only = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><!-- AccessibilityService --></application></manifest>'''
    _, components = shield.manifest_contract(comment_only)
    assert not any("AccessibilityService" in item for item in components)
    registered = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><service android:name=".HakimAccessibilityService" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE" /></application></manifest>'''
    _, components = shield.manifest_contract(registered)
    assert "service:.HakimAccessibilityService" in components
    permissions = shield.manifest_service_permissions(registered)
    assert permissions["service:.HakimAccessibilityService"] == "android.permission.BIND_ACCESSIBILITY_SERVICE"


def test_sensitive_service_exception_is_exact_and_fail_closed(tmp_path):
    prepare_minimal_root(tmp_path)
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(
        '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application>'''
        '''<service android:name=".HakimAccessibilityService" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE" />'''
        '''<service android:name=".OtherAccessibilityService" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE" />'''
        '''</application></manifest>''',
        encoding="utf-8",
    )
    android = {
        "path": "AndroidManifest.xml",
        "forbidden_tokens": [],
        "forbidden_service_tokens": ["AccessibilityService"],
        "approved_sensitive_services": [{
            "token": "AccessibilityService",
            "component": "service:.HakimAccessibilityService",
            "service_permission": "android.permission.BIND_ACCESSIBILITY_SERVICE",
            "requires_local_user_enablement": True,
            "loopback_only": True,
            "financial_safe_mode_gate": True,
        }],
    }
    policy_obj = {
        "fail_closed": True,
        "preserve_outcomes_not_implementations": True,
        "required_paths": [],
        "capabilities": [],
        "protected_success_ids": [],
        "protected_promotion_lineage_ids": [],
        "android_manifest": android,
        "transition_registry": "missing.json",
    }
    violations = shield.static_violations(tmp_path, policy_obj)
    assert any(v.code == "FORBIDDEN_ANDROID_SERVICE" and v.target == "service:.OtherAccessibilityService" for v in violations)
    assert not any(v.code == "FORBIDDEN_ANDROID_SERVICE" and v.target == "service:.HakimAccessibilityService" for v in violations)


def test_sensitive_service_exception_requires_exact_bind_permission(tmp_path):
    prepare_minimal_root(tmp_path)
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(
        '''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application>'''
        '''<service android:name=".HakimAccessibilityService" android:permission="android.permission.INTERNET" />'''
        '''</application></manifest>''',
        encoding="utf-8",
    )
    policy_obj = {
        "fail_closed": True,
        "preserve_outcomes_not_implementations": True,
        "required_paths": [],
        "capabilities": [],
        "protected_success_ids": [],
        "protected_promotion_lineage_ids": [],
        "android_manifest": {
            "path": "AndroidManifest.xml",
            "forbidden_tokens": [],
            "forbidden_service_tokens": ["AccessibilityService"],
            "approved_sensitive_services": [{
                "token": "AccessibilityService",
                "component": "service:.HakimAccessibilityService",
                "service_permission": "android.permission.BIND_ACCESSIBILITY_SERVICE",
                "requires_local_user_enablement": True,
                "loopback_only": True,
                "financial_safe_mode_gate": True,
            }],
        },
        "transition_registry": "missing.json",
    }
    violations = shield.static_violations(tmp_path, policy_obj)
    assert any(v.code == "FORBIDDEN_ANDROID_SERVICE" and v.target == "service:.HakimAccessibilityService" for v in violations)


def test_transition_records_fail_closed_without_proof(tmp_path):
    invalid = {
        "target_type": "path", "target": "app/hakim/core.py", "mode": "RETIRE",
        "rationale": "reason", "authority": "authority", "rollback": "rollback",
        "evidence_tests": ["missing_test.py"], "approved": True,
    }
    assert shield.valid_transition(invalid, tmp_path) is False


def test_independent_continuity_workflow_is_fail_closed_and_has_full_history():
    workflow = (ROOT / ".github/workflows/continuity-shield.yml").read_text(encoding="utf-8")
    assert "push:" in workflow and "pull_request:" in workflow
    assert "contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert "python scripts/hakim_continuity_shield.py" in workflow
    assert "python -m pytest -q tests/test_hakim_continuity_shield.py" in workflow
    assert "HAKIM_SHIELD_BASE_REF" in workflow
