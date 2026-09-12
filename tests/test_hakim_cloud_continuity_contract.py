from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"
WORKFLOW = ROOT / ".github" / "workflows" / "autonomous-continuation.yml"


def test_cloud_continuity_contract_is_single_hakim_safe_and_free_first():
    text = (GOV / "HAKIM_CLOUD_CONTINUITY_AR.md").read_text(encoding="utf-8")
    for token in (
        "ليست منظومة ثانية",
        "محلي أولًا + سحابي مستمر",
        "لا منفذ عام للهاتف",
        "لا تحويل GitHub إلى ناقل أوامر عام للهاتف",
        "لا خدمة مدفوعة",
        "FAIL-CLOSED",
        "cache وسيلة نقل/احتفاظ للحالة",
        "cloud_runtime_continuity",
    ):
        assert token in text


def test_cloud_workflow_prepares_seals_and_saves_only_verified_state():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "*/15 * * * *" in text
    assert "OMEGA_CONTINUITY_SNAPSHOT_DIR" in text
    assert "OMEGA_CONTINUITY_RETENTION: '8'" in text
    assert "omega-apex-state-v2-" in text
    assert "omega-apex-state-" in text  # migration fallback from the prior cache namespace
    assert "python -m app.hakim.run_cloud_continuity prepare" in text
    assert "python -m app.hakim.run_event_once" in text
    assert "id: continuity_seal" in text
    assert "python -m app.hakim.run_cloud_continuity seal" in text
    assert "steps.continuity_seal.outcome == 'success'" in text
    assert "OMEGA_ALLOW_MERGE: 'false'" in text


def test_continuity_shield_protects_cloud_runtime_continuity_as_p0():
    policy = json.loads((GOV / "HAKIM_CONTINUITY_SHIELD.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in policy["capabilities"]}
    capability = by_id["cloud_runtime_continuity"]
    assert capability["tier"] == "P0"
    assert capability["status"] == "PROTECTED_ACTIVE"
    expected_paths = {
        "governance/HAKIM_CLOUD_CONTINUITY_AR.md",
        "app/hakim/cloud_continuity.py",
        "app/hakim/run_cloud_continuity.py",
        ".github/workflows/autonomous-continuation.yml",
    }
    assert expected_paths <= set(capability["paths"])
    assert {
        "tests/test_cloud_continuity.py",
        "tests/test_hakim_cloud_continuity_contract.py",
    } <= set(capability["tests"])
    assert expected_paths <= set(policy["required_paths"])


def test_cloud_continuity_never_promotes_unverified_phone_field_state():
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["field_phone"]["public_command_transport"] is False
    assert state["field_phone"]["public_github_command_relay"] is False
