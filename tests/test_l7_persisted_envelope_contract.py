import json
from pathlib import Path

from app.hakim.autonomy_arena import L7_OPERATIONAL_ENVELOPE
from app.hakim.run_l7_certification_gate import _envelope_payload


def test_persisted_l7_envelope_payload_matches_runtime_contract():
    payload = _envelope_payload()

    assert payload == {
        "capabilities": sorted(L7_OPERATIONAL_ENVELOPE.capabilities),
        "max_risk": L7_OPERATIONAL_ENVELOPE.max_risk,
        "require_reversible_above": L7_OPERATIONAL_ENVELOPE.require_reversible_above,
        "min_evidence": L7_OPERATIONAL_ENVELOPE.min_evidence,
    }


def test_governance_runs_self_describing_l7_gate():
    workflow = Path(".github/workflows/governance.yml").read_text(encoding="utf-8")
    assert "python -m app.hakim.run_l7_certification_gate" in workflow
