from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_best_route_policy_is_one_hakim_and_contains_full_route_bundle():
    text = (ROOT / "governance/HAKIM_BEST_ROUTE_POLICY_AR.md").read_text(encoding="utf-8")
    assert "امتداد لحكيم الواحد فقط" in text
    for term in ("أفضل طريقة", "أفضل أسلوب", "أفضل وسيلة", "أفضل تقنية", "أفضل آلية", "أفضل توقيت"):
        assert term in text
    assert "و؟ → و؟ → و؟ → لِمَ؟ → و؟ → و؟ → اعتمد → أصلح → أكمل → هَيّا" in text
    assert "الترتيب ليس دليل نجاح النتيجة" in text
    assert "حد التنفيذ" in text


def test_runtime_actually_uses_multicriteria_optimizer_before_execution():
    governor = (ROOT / "app/hakim/recovery_governor.py").read_text(encoding="utf-8")
    optimizer = (ROOT / "app/hakim/best_route_optimizer.py").read_text(encoding="utf-8")
    assert "optimize_routes" in governor
    assert 'stage="selection"' in governor
    assert 'stage="execution"' in governor
    assert "RANKED_NOT_OUTCOME_PROOF" in governor
    for criterion in (
        "fit", "evidence", "expected_success", "safety_margin", "burden",
        "monetary_cost", "external_dependency", "independence", "sustainability", "speed",
    ):
        assert criterion in optimizer
    assert "pareto_dominated" in optimizer
