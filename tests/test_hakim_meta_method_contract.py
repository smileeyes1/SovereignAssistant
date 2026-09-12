import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / "governance"


def test_hakim_meta_method_is_single_hakim_extension():
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    assert "امتداد منهجي لحكيم الواحد" in meta
    assert "لا ينشئ كيانًا موازيًا" in meta
    assert "حكيم الواحد" in meta


def test_meta_method_has_all_governing_engines():
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    required = [
        "كل شيء⁶",
        "كيف السباعية★",
        "ابتكر★",
        "الحكمة★",
        "بكل شيء★",
        "ن★",
        "أضعف حلقة",
        "أعلى رافعة",
        "الدليل المضاد",
        "نقطة الثبات",
        "التعلم المركب",
        "الاستقلالية",
        "الأتمتة",
    ]
    for token in required:
        assert token in meta, token


def test_nstar_controls_depth_and_prevents_recursive_explosion():
    nstar = (GOV / "HAKIM_NSTAR_SPEC_AR.md").read_text(encoding="utf-8")
    assert "governance/HAKIM_META_METHOD_AR.md" in nstar
    assert "DELTA المادي الصافي" in nstar
    assert "انفجار تكراري" in nstar
    assert "NO_OP" in nstar


def test_context_seed_restores_meta_method_without_replacing_core():
    seed = (GOV / "HAKIM_CONTEXT_SEED_AR.txt").read_text(encoding="utf-8")
    assert "منهج حكيم الأعلى مفعّل تحت حكيم الواحد" in seed
    assert "governance/HAKIM_META_METHOD_AR.md" in seed
    assert "governance/HAKIM_CANONICAL_CORE_AR.md" in seed
    assert "RELEASE_BUILD→VALIDATOR_GATE→FINALIZE→DELIVER" in seed


def test_active_restore_sequence_loads_meta_method_explicitly():
    active = json.loads((GOV / "HAKIM_ACTIVE.json").read_text(encoding="utf-8"))
    assert active["meta_method_spec"] == "governance/HAKIM_META_METHOD_AR.md"
    assert "LOAD_META_METHOD_SPEC" in active["restore_sequence"]
    assert active["restore_sequence"].index("LOAD_META_METHOD_SPEC") > active["restore_sequence"].index("LOAD_NSTAR_SPEC")
    assert active["restore_sequence"].index("LOAD_META_METHOD_SPEC") < active["restore_sequence"].index("LOAD_PHONE_SOVEREIGN_CONSTRAINTS")


def test_meta_method_does_not_claim_physical_field_success():
    meta = (GOV / "HAKIM_META_METHOD_AR.md").read_text(encoding="utf-8")
    assert "FIELD_VERIFIED=true" not in meta
    assert "physical_phone_round_trip=PASS" not in meta
