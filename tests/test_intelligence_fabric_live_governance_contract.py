from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_recovery_governor_contains_live_intelligence_boundary():
    text = (ROOT / "app/hakim/recovery_governor.py").read_text(encoding="utf-8")
    assert "select_intelligence" in text
    assert 'stage="selection"' in text
    assert 'stage="execution"' in text
    assert "ROUTED_NOT_METHOD_EXECUTION_PROOF" in text
    assert "intelligence fabric mandatory guards missing" in text


def test_production_composition_root_still_uses_the_governed_recovery_governor():
    text = (ROOT / "app/hakim/production.py").read_text(encoding="utf-8")
    assert "governor = RecoveryGovernor(registry, state)" in text
    assert "engine = governor.engine()" in text
