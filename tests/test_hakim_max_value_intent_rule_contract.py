from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"
LEXICAL_PROMOTION = "82fb26cede5400d3491b92c89c11783454847143"
FROZEN_PHONE_PROMOTION = "a6225e4118d68871ed00c8328f072fd8bd15bfc6"


def test_max_value_rule_contract():
    text = (GOV / "HAKIM_MAX_VALUE_INTENT_RULE_AR.md").read_text(encoding="utf-8")
    required = [
        "تعظيم تحقيق غايته نفسها إلى أعلى قيمة صافية مثبتة داخل العقد",
        "INTENT_MAXIMIZE_NET_VALUE=ON",
        "AUTONOMY_DEFAULT=ON",
        "USE_ALL_MATERIALLY_RELEVANT_SAFE_ALLOWED_MEANS=ON",
        "ROOT_CAUSE_AND_HIGHEST_LEVERAGE=ON",
        "ACTUAL_OUTPUT_VERIFICATION=ON",
        "REGRESSION_AND_INTEGRATION=ON",
        "STOP_AT_STABILITY_POINT=ON",
        "RESTORE_REQUIRED=ON",
        "PROMOTION_GATE_REQUIRED=ON",
        "RESTORE_TOKEN=LOAD_MAX_VALUE_INTENT_RULE",
        "PROMOTION_TOKEN=MAX_VALUE_INTENT_RULE_CONTRACT_PASS",
        "كل شيء مفيد",
        "لا تعني «كل شيء» الاستمرار بلا نهاية",
        "LAST_VERIFIED_BASELINE",
        "PROVEN_SUCCESS",
        "FIELD_VERIFIED",
    ]
    for token in required:
        assert token in text


def test_user_lexical_intensifiers_are_explicitly_semantic_and_bounded():
    text = (GOV / "HAKIM_MAX_VALUE_INTENT_RULE_AR.md").read_text(encoding="utf-8")
    required = [
        "المكثفات اللفظية الحاكمة",
        "«كمال/بكمال»",
        "«علو/أعلى»",
        "«حكمة/أحكم»",
        "«خبرة/أخبر»",
        "«شمول/أشمل»",
        "«اكتمال/أكمل»",
        "رفع سقف الجودة والدقة والموثوقية إلى أعلى مستوى مثبت ومتاح داخل العقد",
        "ترجيح الفعل الأنسب بالقدر والوقت والوسيلة مع تقدير العواقب وقابلية الرجوع",
        "استحضار أنسب معرفة وأدوات ومصادر واختبارات وتخصصات منطقية ذات صلة بقدر أثرها",
        "إغلاق الفجوات المادية الآمنة القابلة للإغلاق",
        "تغطية جميع الجوانب والمحاور المؤثرة ماديًا",
        "لا يمنح صلاحيات إضافية",
    ]
    for token in required:
        assert token in text


def test_lexical_intensifiers_are_durably_promoted_without_field_overclaim():
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["promotion_lineage"]["max_value_lexical_intensifiers_v1"] == LEXICAL_PROMOTION
    assert "max_value_lexical_intensifiers_v1" in state["proven_success"]
    for key in (
        "max_value_lexical_intensifiers_contract_main",
        "max_value_lexical_intensifiers_governance_main",
        "max_value_lexical_intensifiers_continuity_main",
        "max_value_lexical_intensifiers_reality_main",
    ):
        assert state["promotion_evidence"][key] == "PASS"
    assert state["governance_verified_main"] == LEXICAL_PROMOTION
    assert state["freshness_observed_main"] == LEXICAL_PROMOTION
    assert state["freshness_state_refresh_source_main"] == LEXICAL_PROMOTION
    assert state["last_verified_baseline"] == FROZEN_PHONE_PROMOTION
    assert state["latest_observed_main"] == FROZEN_PHONE_PROMOTION
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"


def test_active_pointer_names_rule_without_changing_frozen_restore_contract():
    """Stable contract id retained; 2.3 intentionally promotes the rule into the restore contract."""
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["version"] == "2.3"
    assert active["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    restore = active["restore_sequence"]
    promotion = active["promotion_gate"]
    assert "LOAD_MAX_VALUE_INTENT_RULE" in restore
    assert restore.index("LOAD_META_METHOD_SPEC") < restore.index("LOAD_MAX_VALUE_INTENT_RULE")
    assert restore.index("LOAD_MAX_VALUE_INTENT_RULE") < restore.index("LOAD_VALUE_GATES_SPEC")
    assert "MAX_VALUE_INTENT_RULE_CONTRACT_PASS" in promotion
    assert promotion.index("INTELLIGENCE_FABRIC_CONTRACT_PASS") < promotion.index("MAX_VALUE_INTENT_RULE_CONTRACT_PASS")
    assert promotion.index("MAX_VALUE_INTENT_RULE_CONTRACT_PASS") < promotion.index("VALUE_GATES_CONTRACT_PASS")


def test_seed_restores_rule_and_matches_active_contract():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    assert active["max_value_intent_rule"] in seed
    assert "RESTORE_REQUIRED=ON" in seed
    assert "PROMOTION_GATE_REQUIRED=ON" in seed
    assert "LOAD_MAX_VALUE_INTENT_RULE" in seed
    assert "MAX_VALUE_INTENT_RULE_CONTRACT_PASS" in seed
    encoded_restore = "→".join(active["restore_sequence"])
    assert encoded_restore in seed


def test_loaded_meta_method_integrates_rule_semantics():
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    assert "HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in meta
    assert "أعلى قيمة صافية مثبتة داخل العقد" in meta
    assert "LAST_VERIFIED_BASELINE" in meta
    assert "PROVEN_SUCCESS" in meta
    assert "FREEZE_BASELINE/NO_OP" in meta
