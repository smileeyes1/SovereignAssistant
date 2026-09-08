from pathlib import Path


def test_l7_soak_includes_injected_failure_rollback_restart_and_audit():
    source = Path("app/hakim/run_arena_gate.py").read_text(encoding="utf-8")
    start = source.index("def bounded_soak_continuity_probe")
    end = source.index("\ndef main()", start)
    probe = source[start:end]
    for required in (
        "should_fail",
        "rolled_back",
        "run.recovered",
        "restarted",
        "OutcomeAudit",
        "recovered-89",
    ):
        assert required in probe


def test_l7_roadmap_requires_faulted_soak_evidence():
    roadmap = Path("app/hakim/autonomy_roadmap.py").read_text(encoding="utf-8")
    assert "long-duration soak includes injected failures recovery rollback and outcome audit" in roadmap
