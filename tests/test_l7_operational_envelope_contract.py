from pathlib import Path
from tempfile import TemporaryDirectory

from app.hakim.autonomy_arena import (
    L7_OPERATIONAL_ENVELOPE,
    ArenaScenario,
    AutonomyArena,
    OmegaLevel,
)
from app.hakim.durable_state import DurableStateStore
from app.hakim.mission_autonomy import BoundedMissionRunner, OutcomeAudit
from app.hakim.mission_kernel import OperationalEnvelope


L7_CATEGORIES = (
    "mission-autonomy",
    "mission-safety",
    "mission-recovery",
    "self-improvement",
    "long-duration",
)


def _l7_scenarios() -> tuple[ArenaScenario, ...]:
    return tuple(
        ArenaScenario(f"l7-{category}", category, 5, OmegaLevel.L7, lambda: True)
        for category in L7_CATEGORIES
    )


def test_l7_certificate_carries_supported_operational_envelope():
    arena = AutonomyArena()
    scenarios = _l7_scenarios()

    cert = arena.certify(OmegaLevel.L7, scenarios, arena.run(scenarios))

    assert cert.certified is True
    assert cert.operational_envelope == L7_OPERATIONAL_ENVELOPE


def test_l7_rejects_certificate_outside_supported_operational_envelope():
    arena = AutonomyArena()
    scenarios = _l7_scenarios()
    broader = OperationalEnvelope(
        frozenset({"*"}),
        max_risk=3,
        require_reversible_above=3,
        min_evidence=0,
    )

    cert = arena.certify(
        OmegaLevel.L7,
        scenarios,
        arena.run(scenarios),
        operational_envelope=broader,
    )

    assert cert.certified is False
    assert "unsupported operational envelope for L7" in cert.reasons
    assert cert.operational_envelope == broader


def test_l7_certification_scope_matches_bounded_mission_runner_default():
    with TemporaryDirectory() as tmp:
        runner = BoundedMissionRunner(OutcomeAudit(DurableStateStore(Path(tmp) / "omega.db")))

        assert runner.mission_kernel.envelope == L7_OPERATIONAL_ENVELOPE
