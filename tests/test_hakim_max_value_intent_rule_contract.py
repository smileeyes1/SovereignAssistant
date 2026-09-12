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


def test_active_pointer_loads_rule_before_value_gates():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["max_value_intent_rule"] == "governance/HAKIM_MAX_VALUE_INTENT_RULE_AR.md"
    seq = active["restore_sequence"]
    assert seq.index("LOAD_MAX_VALUE_INTENT_RULE") < seq.index("LOAD_VALUE_GATES_SPEC")
    assert "MAX_VALUE_INTENT_RULE_CONTRACT_PASS" in active["promotion_gate"]
