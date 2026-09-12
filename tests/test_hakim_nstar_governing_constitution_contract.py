import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_nstar_governing_constitution_is_single_hakim_extension():
    text = (GOV / "HAKIM_NSTAR_GOVERNING_CONSTITUTION_AR.md").read_text(encoding="utf-8")
    assert "داخل حكيم الواحد" in text
    assert "لا ينشئ حكيمًا ثانيًا" in text
    assert "لا يتوقف المقصد بفشل الوسيلة" in text


def test_nstar_governing_constitution_captures_latest_governing_contract():
    text = (GOV / "HAKIM_NSTAR_GOVERNING_CONSTITUTION_AR.md").read_text(encoding="utf-8")
    required = [
        "ن★ ليست عددًا ثابتًا",
        "كل مصدر أو أداة أو دليل موثوق ونافع",
        "أي فجوة مادية آمنة قابلة للإغلاق تمنع إعلان الاكتمال",
        "الأحدث الصريح يعلو",
        "المهمة المؤقتة لا تصبح قاعدة عامة",
        "البيانات الحساسة لا تتحول إلى قاعدة أو ملف عام",
        "عند الفعل عالي الأثر",
        "التحقق من الناتج الفعلي",
        "فحص الانحدار والتكامل",
        "UPDATE_STATE → VERIFY_STILL_TRUE → REUSE_NOW → REPLAN_IF_BETTER → CONTINUE",
    ]
    for token in required:
        assert token in text, token


def test_active_pointer_restores_governing_constitution():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["nstar_governing_constitution"] == "governance/HAKIM_NSTAR_GOVERNING_CONSTITUTION_AR.md"
    seq = active["restore_sequence"]
    assert "LOAD_NSTAR_GOVERNING_CONSTITUTION" in seq
    assert seq.index("LOAD_NSTAR_GOVERNING_CONSTITUTION") > seq.index("LOAD_NSTAR_SPEC")
    assert seq.index("LOAD_NSTAR_GOVERNING_CONSTITUTION") < seq.index("LOAD_META_METHOD_SPEC")


def test_runtime_already_enforces_constitution_semantics():
    runtime = json.loads((GOV / "HAKIM_RUNTIME_POLICY_v2.json").read_text(encoding="utf-8"))
    adaptive = runtime["adaptive_intelligence"]
    autonomy = runtime["autonomy"]
    assert adaptive["enabled"] is True
    assert adaptive["dynamic_depth"] is True
    assert "HOW_ITSELF" in adaptive["apply_to"]
    assert adaptive["increase_depth_while"] == "MATERIAL_NET_GAIN_EXPECTED_OR_PROVEN"
    assert autonomy["execute_safe_available_steps_automatically"] is True
    assert autonomy["no_claim_without_evidence"] is True
    assert runtime["failure_rule"] == "GOAL_DOES_NOT_FAIL_WHEN_A_MEANS_FAILS"
    assert runtime["zero_burden"] is True


def test_seed_and_state_keep_nstar_durable():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert "ن★ هي سياسة الذكاء التكيفي الحاكمة" in seed
    assert "AUTONOMY_DEFAULT=ON" in seed
    assert "nstar_adaptive_intelligence_extension_v2_1" in state["proven_success"]


def test_no_unverified_physical_phone_promotion():
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
