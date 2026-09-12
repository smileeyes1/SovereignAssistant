from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


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
        "كل شيء مفيد",
        "لا تعني «كل شيء» الاستمرار بلا نهاية",
        "LAST_VERIFIED_BASELINE",
        "PROVEN_SUCCESS",
        "FIELD_VERIFIED",
    ]
    for token in required:
        assert token in text


def test_active_pointer_names_rule_without_changing_frozen_restore_contract():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["version"] == "2.2"
    assert active["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    assert "LOAD_MAX_VALUE_INTENT_RULE" not in active["restore_sequence"]
    assert "MAX_VALUE_INTENT_RULE_CONTRACT_PASS" not in active["promotion_gate"]


def test_loaded_meta_method_integrates_rule_semantics():
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    assert "HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in meta
    assert "أعلى قيمة صافية مثبتة داخل العقد" in meta
    assert "LAST_VERIFIED_BASELINE" in meta
    assert "PROVEN_SUCCESS" in meta
    assert "FREEZE_BASELINE/NO_OP" in meta
