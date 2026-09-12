from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_max_value_rule_is_explicitly_protected_by_continuity_shield():
    policy = json.loads((GOV / "HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))
    assert "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in policy["required_paths"]
    capabilities = {item["id"]: item for item in policy["capabilities"]}
    cap = capabilities["max_value_intent_rule"]
    assert cap["tier"] == "P0"
    assert cap["status"] == "PROTECTED_ACTIVE"
    assert "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in cap["paths"]
    assert "tests/test_hakim_max_value_intent_rule_contract.py" in cap["tests"]


def test_autonomous_mutation_guard_is_p0_and_protects_both_mutation_surfaces():
    policy = json.loads((GOV / "HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))
    capabilities = {item["id"]: item for item in policy["capabilities"]}
    cap = capabilities["autonomous_mutation_guard"]
    assert cap["tier"] == "P0"
    assert cap["status"] == "PROTECTED_ACTIVE"
    assert "app/hakim/github_control.py" in cap["paths"]
    assert "app/hakim/development_actions.py" in cap["paths"]
    assert "tests/test_github_control.py" in cap["tests"]
    assert "tests/test_development_actions.py" in cap["tests"]


def test_mutation_surfaces_are_public_api_guarded_by_continuity_shield():
    policy = json.loads((GOV / "HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))
    assert "app/hakim/github_control.py" in policy["api_surface_files"]
    assert "app/hakim/development_actions.py" in policy["api_surface_files"]
