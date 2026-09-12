from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "governance" / "HAKIM_ACTIVE.json"
SPEC = ROOT / "governance" / "HAKIM_CLOUD_CONTINUITY_AR.md"
WORKFLOW = ROOT / ".github" / "workflows" / "autonomous-continuation.yml"


def load_active():
    return json.loads(ACTIVE.read_text(encoding="utf-8"))


def test_cloud_continuity_is_loaded_by_the_single_active_hakim():
    active = load_active()
    assert active["cloud_continuity_spec"] == "governance/HAKIM_CLOUD_CONTINUITY_AR.md"
    assert SPEC.is_file()
    assert "LOAD_CLOUD_CONTINUITY_SPEC" in active["restore_sequence"]
    assert "CLOUD_CONTINUITY_CONTRACT_PASS" in active["promotion_gate"]


def test_cloud_continuity_contract_preserves_single_hakim_and_no_public_phone_ingress():
    text = SPEC.read_text(encoding="utf-8")
    assert "ليست منظومة ثانية" in text
    assert "محلي أولًا + سحابي مستمر" in text
    assert "لا منفذ عام للهاتف" in text
    assert "لا تحويل GitHub إلى ناقل أوامر عام للهاتف" in text
    assert "لا خدمة مدفوعة" in text
    assert "FAIL-CLOSED" in text


def test_cloud_workflow_verifies_before_use_and_only_saves_after_successful_seal():
    text = WORKFLOW.read_text(encoding="utf-8")
    prepare = "python -m app.hakim.run_cloud_continuity prepare"
    process = "python -m app.hakim.run_event_once"
    seal = "python -m app.hakim.run_cloud_continuity seal"
    save_guard = "steps.continuity_seal.outcome == 'success'"
    assert prepare in text and process in text and seal in text
    assert text.index(prepare) < text.index(process) < text.index(seal)
    assert save_guard in text
    assert "omega-apex-state-v2-" in text


def test_active_version_remains_compatible_with_existing_active_state_contract():
    state = json.loads((ROOT / "governance" / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["active_extension_version"] == load_active()["version"]
    assert state["field_phone"]["field_verified"] is False
