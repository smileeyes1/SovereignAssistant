import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def text(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def test_universal_constitution_is_general_and_layered():
    c = text("OMEGA_SOVEREIGN_OPERATING_CONSTITUTION.md")
    required = [
        "UNIVERSAL CONSTITUTION → DOMAIN/PROJECT PROFILE → CURRENT STATE CAPSULE → EXECUTION",
        "ركن الغاية والعقد",
        "ركن الواقع قبل الادعاء",
        "فرض التنفيذ الذاتي",
        "فرض الاستمرار",
        "فرض السببية",
        "فرض التحقيق والدليل",
        "فرض حماية الناجح",
        "فرض عدم الانحدار",
        "فرض أقل كلفة كاملة",
        "فرض الاستقلال والملكية",
        "فرض السلطة البشرية",
        "فرض أمن الأسرار والصلاحيات",
        "فرض اختيار الأدوات",
        "فرض فصل المعنى عن العرض",
        "فرض الموارد والسياق",
        "فرض الأتمتة الذكية",
        "فرض الحالة والاستعادة",
        "فرض جودة الإغلاق",
    ]
    for marker in required:
        assert marker in c

    # Mutable project/device state must not leak into the universal layer.
    forbidden = [
        "1c5525fd90b02c9f3e251353c1ab436737620ec3",
        "a62001650811645620c8639a39581f2274c99a9b",
        "TECNO POVA 7 / Android 15 / SDK 35",
        "Issue #42",
        "hakim-companion-45bc7cb6f926",
    ]
    for marker in forbidden:
        assert marker not in c

    # The manifest forbids mutable_sha as a class, not only known historical SHAs.
    # Reject any concrete 40-hex Git commit identity in the universal constitution.
    assert re.search(r"\b[0-9a-f]{40}\b", c, flags=re.IGNORECASE) is None


def test_chatgpt_adapter_respects_real_platform_authority_and_trigger_limits():
    a = text("CHATGPT_GENERAL_ASSISTANT_ADAPTER.md")
    assert "تعليمات النظام/المطور" in a
    assert "المستخدم الأحدث والأخص" in a
    assert "Automation/Trigger" in a
    assert "المحادثة وحدها ليست Trigger ذاتيًا" in a
    assert "Human Gate" in a
    assert "لا تدّع تنفيذًا أو PASS بلا أثر أداة/دليل مناسب" in a


def test_domain_profile_and_state_capsule_are_separated():
    p = text("DOMAIN_PROFILE_TEMPLATE.md")
    s = text("STATE_CAPSULE_TEMPLATE.md")
    assert "Protected Invariants / Golden Baselines" in p
    assert "بوابات التحقق" in p
    assert "ممنوع" in p and "STATE_CAPSULE_TEMPLATE.md" in p
    assert "Mutable recovery hint, not constitution" in s
    assert "Last Verified Baseline" in s
    assert "PROVEN" in s and "NOT_PROVEN" in s and "BLOCKED" in s
    assert "Staleness Rule" in s


def test_hakim_continuation_is_profile_not_universal_constitution():
    h = text("HAKIM_SOVEREIGN_AUTONOMOUS_CONTINUATION.md")
    assert "OMEGA_SOVEREIGN_OPERATING_CONSTITUTION.md" in h
    assert "Profile" in h or "profile" in h
    assert "RECOVERY HINT" in h
    assert "HAKIM_STATE_CAPSULE.md" in h

    # Profiles are durable policy, not mutable state. Keep SHA/CI/blockers in the capsule.
    assert re.search(r"\b[0-9a-f]{40}\b", h) is None
    assert "current field blocker =" not in h.lower()
    assert "Governance = PASS" not in h
    assert "Reality = PASS" not in h


def test_hakim_state_capsule_is_explicitly_mutable_and_evidence_scoped():
    s = text("HAKIM_STATE_CAPSULE.md")
    required = [
        "Mutable recovery hint, not constitution",
        "Last Verified Baseline",
        "PROVEN",
        "NOT_PROVEN",
        "FAIL",
        "BLOCKED",
        "Protected Invariants",
        "Open Work in Causal Order",
        "External / Human Gates",
        "Recovery Path",
        "Staleness Rule",
        "RECOVERY HINT ONLY",
    ]
    for marker in required:
        assert marker in s
    assert "CI/runtime only" in s
    assert "does not imply Android Companion field qualification" in s
    assert "Remote Desktop Commander remains optional maintenance only" in s
    assert "no resident local model" in s


def test_amendment_protocol_is_fail_closed_and_post_merge_verified():
    p = text("CONSTITUTION_AMENDMENT_PROTOCOL.md")
    required = [
        "سبب التغيير",
        "حفظ العقد",
        "فصل الطبقات",
        "Impact Diff",
        "Regression Gate",
        "Head identity",
        "Post-merge verification",
        "NOT_PROVEN",
    ]
    for marker in required:
        assert marker in p


def test_machine_readable_manifest_matches_constitution_contract():
    m = json.loads(text("OMEGA_CONSTITUTION_MANIFEST.json"))
    assert m["schema_version"] == 1
    assert m["canonical_file"] == "docs/OMEGA_SOVEREIGN_OPERATING_CONSTITUTION.md"
    assert m["amendment_protocol"] == "docs/CONSTITUTION_AMENDMENT_PROTOCOL.md"
    assert m["layers"] == [
        "UNIVERSAL_CONSTITUTION",
        "DOMAIN_OR_PROJECT_PROFILE",
        "CURRENT_STATE_CAPSULE",
        "EXECUTION",
    ]
    assert set(m["official_evidence_states"]) == {"PROVEN", "NOT_PROVEN", "FAIL", "BLOCKED"}
    assert "new_permission" in m["human_gate_required_for"]
    assert "mutable_sha" in m["forbidden_in_universal_layer"]
    assert "device_specific_baseline" in m["forbidden_in_universal_layer"]
    assert m["automation_preference"][0] == "event_driven"
    assert m["automation_preference"][-1] == "local_durable_runtime_or_queue"
