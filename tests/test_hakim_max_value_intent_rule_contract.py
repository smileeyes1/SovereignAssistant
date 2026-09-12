from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_max_value_rule_exists_and_is_single_hakim_extension():
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
        "لا تنشئ حكيمًا ثانيًا",
        "FREEZE_BASELINE",
        "FIELD_VERIFIED",
    ]
    for token in required:
        assert token in text


def test_active_pointer_loads_max_value_rule():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    assert "LOAD_MAX_VALUE_INTENT_RULE" in active["restore_sequence"]


def test_nstar_and_meta_method_reference_rule():
    nstar = (GOV / "HAKIM_NSTAR_SPEC_AR.md").read_text(encoding="utf-8")
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    assert "HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in nstar
    assert "HAKIM_MAX_VALUE_INTENT_RULE_AR.md" in meta
