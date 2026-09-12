import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_value_gates_are_single_hakim_extension():
    text = (GOV / "HAKIM_VALUE_GATES_AR.md").read_text(encoding="utf-8")
    assert "امتداد تشغيلي داخل «حكيم الواحد»" in text
    assert "لا ينشئ كيانًا أو طبقة قيادة موازية" in text
    assert "لا تستبدل أيًا منها ولا تنشئ حاكمًا موازيًا" in text


def test_value_gates_cover_material_value_dimensions():
    text = (GOV / "HAKIM_VALUE_GATES_AR.md").read_text(encoding="utf-8")
    required = [
        "بوابة الغاية والعقد",
        "بوابة الحقيقة والدليل",
        "بوابة الشرع والأمان والحقوق والسلطة",
        "بوابة الشمول",
        "بوابة التكامل",
        "بوابة الحكمة والترجيح",
        "بوابة الابتكار",
        "بوابة التنفيذ الأدنى عبئًا",
        "بوابة الناتج الفعلي",
        "بوابة التحقق المستقل والعدائي",
        "بوابة إصلاح السبب",
        "بوابة التعلم المركب",
        "بوابة اللغة والتصميم وتجربة المستخدم",
        "بوابة القيمة النهائية",
    ]
    for token in required:
        assert token in text, token


def test_value_gates_preserve_nstar_adaptive_depth_and_stop_rule():
    text = (GOV / "HAKIM_VALUE_GATES_AR.md").read_text(encoding="utf-8")
    assert "DELTA مادي صافي موجب" in text
    assert "لا تكرر بلا معرفة جديدة" in text
    assert "FREEZE_BASELINE/NO_OP" in text
    assert "كل ما يفيد، لا كل ما يوجد" in text


def test_value_gates_enforce_actual_output_and_root_cause_recovery():
    text = (GOV / "HAKIM_VALUE_GATES_AR.md").read_text(encoding="utf-8")
    assert "ACTUAL_OUTPUT هو الحكم" in text
    assert "شخّص السبب الجذري" in text
    assert "لا يتوقف المقصد بفشل الوسيلة" in text
    assert "PROVEN_SUCCESS" in text
    assert "ROLLBACK" in text


def test_active_restore_sequence_loads_value_gates():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["value_gates_spec"] == "governance/HAKIM_VALUE_GATES_AR.md"
    assert "LOAD_VALUE_GATES_SPEC" in active["restore_sequence"]
    assert active["restore_sequence"].index("LOAD_VALUE_GATES_SPEC") > active["restore_sequence"].index("LOAD_META_METHOD_SPEC")
    assert active["restore_sequence"].index("LOAD_VALUE_GATES_SPEC") < active["restore_sequence"].index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS")
    assert "VALUE_GATES_CONTRACT_PASS" in active["promotion_gate"]


def test_context_seed_restores_value_gates_without_parallel_hakim():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    assert "بوابات القيمة والأثر ن★ جزء من حكيم الواحد لا منظومة موازية" in seed
    assert "governance/HAKIM_VALUE_GATES_AR.md" in seed
    assert "LOAD_VALUE_GATES_SPEC" in seed
    assert "لا تُغفل رافعة قيمة مؤثرة مذكورة أو غير مذكورة" in seed


def test_value_gates_do_not_claim_unverified_field_success():
    text = (GOV / "HAKIM_VALUE_GATES_AR.md").read_text(encoding="utf-8")
    forbidden = [
        "FIELD_VERIFIED=true",
        "physical_phone_round_trip=PASS",
        "كل شيء نجح فعليًا",
    ]
    for token in forbidden:
        assert token not in text
