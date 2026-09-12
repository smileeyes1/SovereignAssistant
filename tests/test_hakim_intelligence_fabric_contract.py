import json
from pathlib import Path

from app.hakim.intelligence_fabric import FAMILIES

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def _json(name):
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def test_intelligence_fabric_is_single_hakim_layer_not_parallel_identity():
    text = (GOV / "HAKIM_INTELLIGENCE_FABRIC_AR.md").read_text(encoding="utf-8")
    assert "داخل حكيم الواحد" in text
    assert "لا تنشئ عقلًا أو وكيلًا موازيًا" in text
    assert "لا تدّعي امتلاك «كل ذكاء موجود» حرفيًا" in text
    assert "كل ما يضيف قيمة مادية" in text


def test_active_pointer_loads_fabric_and_matrix_before_meta_method():
    active = _json("HAKIM_ACTIVE.json")
    seq = active["restore_sequence"]
    assert active["version"] == "2.3"
    assert active["intelligence_fabric_spec"] == "governance/HAKIM_INTELLIGENCE_FABRIC_AR.md"
    assert active["intelligence_matrix"] == "governance/HAKIM_INTELLIGENCE_MATRIX.json"
    assert seq.index("LOAD_NSTAR_GOVERNING_CONSTITUTION") < seq.index("LOAD_INTELLIGENCE_FABRIC_SPEC")
    assert seq.index("LOAD_INTELLIGENCE_FABRIC_SPEC") < seq.index("LOAD_INTELLIGENCE_MATRIX")
    assert seq.index("LOAD_INTELLIGENCE_MATRIX") < seq.index("LOAD_META_METHOD_SPEC")
    assert "INTELLIGENCE_FABRIC_CONTRACT_PASS" in active["promotion_gate"]


def test_machine_matrix_and_runtime_registry_are_in_lockstep():
    matrix = _json("HAKIM_INTELLIGENCE_MATRIX.json")
    code_names = {family.name for family in FAMILIES}
    matrix_names = {item["id"] for item in matrix["families"]}
    assert code_names == matrix_names
    assert len(code_names) >= 24
    assert matrix["nstar_controls_depth"] is True
    assert matrix["principle"] == "ALL_MATERIALLY_USEFUL_INTELLIGENCE_NOT_ALL_AVAILABLE_INTELLIGENCE"


def test_runtime_routes_fabric_under_nstar_and_preserves_evidence_gate():
    runtime = _json("HAKIM_RUNTIME_POLICY_v2.json")
    fabric = runtime["intelligence_fabric"]
    assert runtime["version"] == "2.1"
    assert fabric["enabled"] is True
    assert fabric["nstar_controls_depth"] is True
    assert fabric["method_claim_requires_execution_evidence"] is True
    assert fabric["selection"] == "MATERIAL_NET_VALUE_OR_MANDATORY_GUARD"
    assert "ROUTE_INTELLIGENCE_FABRIC" in runtime["core_loop"]
    assert runtime["core_loop"].index("ROUTE_INTELLIGENCE_FABRIC") < runtime["core_loop"].index("PLAN")
    assert runtime["actual_output_is_final_judge"] is True


def test_context_seed_restores_fabric_without_weakening_phone_sovereignty():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    phone = _json("HAKIM_PHONE_SOVEREIGN_CONSTRAINTS.json")
    state = _json("HAKIM_ACTIVE_STATE.json")
    assert "نسيج الذكاء الشامل داخل حكيم الواحد" in seed
    assert "HAKIM_INTELLIGENCE_FABRIC_AR.md" in seed
    assert "HAKIM_INTELLIGENCE_MATRIX.json" in seed
    assert phone["priority"] == "P0"
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"


def test_governance_spec_covers_core_intelligence_dimensions_and_anti_hype_guards():
    text = (GOV / "HAKIM_INTELLIGENCE_FABRIC_AR.md").read_text(encoding="utf-8")
    required = [
        "الذكاء المعرفي/الدليلي",
        "الذكاء المنطقي",
        "الذكاء الاستقرائي والاحتمالي",
        "الذكاء السببي والمضاد للواقع",
        "الذكاء الرياضي والكمي",
        "الذكاء الخوارزمي والحاسوبي",
        "الذكاء النظمي والمعماري",
        "ذكاء القرار والاستراتيجية",
        "الذكاء الإبداعي",
        "الذكاء النقدي والعدائي",
        "الذكاء اللغوي والدلالي والبلاغي",
        "الذكاء البصري/المكاني/الإدراكي",
        "الذكاء الأمني والخصوصي",
        "الذكاء التشغيلي التنفيذي",
        "ذكاء الذاكرة والحالة والتعلم",
        "الذكاء فوق المعرفي",
        "ذكاء التجميع/اللجان",
        "الذكاء الزمني والاستشرافي",
        "ذكاء القياس والتجريب",
        "ذكاء التبسيط والاقتصاد",
        "مساواة كثرة المصادر بالصحة",
        "النجاح يثبت فقط بدليل على الناتج الفعلي",
    ]
    for token in required:
        assert token in text, token
