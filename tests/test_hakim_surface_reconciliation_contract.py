from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_surface_reconciliation_contract_is_single_hakim_and_fail_closed():
    text = (GOV / "HAKIM_SURFACE_RECONCILIATION_AR.md").read_text(encoding="utf-8")
    required = [
        "منع انقسام حكيم",
        "المصدر التنفيذي الحاكم",
        "HAKIM_ACTIVE.json",
        "SAVED",
        "LOADED",
        "ACTIVATED",
        "EXECUTED",
        "TESTED",
        "BEHAVIORALLY_PROVEN",
        "SAVED≠LOADED",
        "CANONICAL_REPO → COMPILED_VIEW / KNOWLEDGE_COPY / RECOVERY_COPY",
        "لا توجد مزامنة ثنائية عمياء",
        "لا يقال «حكيم في Gemini مطبّق/مثبت سلوكيًا» إلا بعد دليل",
        "UNQUALIFIED",
        "لا يرفع FIELD_VERIFIED",
    ]
    for token in required:
        assert token in text


def test_surface_contract_preserves_active_max_value_rule_and_field_truth():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert active["version"] == "2.3"
    assert active["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    assert "LOAD_MAX_VALUE_INTENT_RULE" in active["restore_sequence"]
    assert "MAX_VALUE_INTENT_RULE_CONTRACT_PASS" in active["promotion_gate"]
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"


def test_external_surfaces_never_outrank_merged_canonical_by_storage_alone():
    text = (GOV / "HAKIM_SURFACE_RECONCILIATION_AR.md").read_text(encoding="utf-8")
    assert "لا تصبح مسودة أو فرع أو ملف خارجي أو نسخة منسوخة مصدرًا تنفيذيًا لمجرد أنها أحدث نصًا أو أطول أو محفوظة بنجاح" in text
    assert "VIEW/DERIVATIVE" in text
    assert "الرجوع من سطح خارجي إلى المستودع يتم فقط كاقتراح تغيير" in text
    assert "وجود النص في Drive أو المكتبة أو المحادثة لا يثبت إضافته إلى معرفة Gem" in text
