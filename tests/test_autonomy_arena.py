from app.hakim.autonomy_arena import ArenaScenario, AutonomyArena, OmegaLevel, baseline_scenarios


def test_arena_catches_false_pass_and_exceptions():
    arena = AutonomyArena()
    scenarios = (
        ArenaScenario("ok", "runtime", 2, OmegaLevel.L1, lambda: True),
        ArenaScenario("false", "events", 3, OmegaLevel.L1, lambda: False),
        ArenaScenario("boom", "safety", 5, OmegaLevel.L1, lambda: (_ for _ in ()).throw(RuntimeError("fault"))),
    )
    report = arena.run(scenarios)
    assert report.passed is False
    assert report.pass_rate == 1 / 3
    assert {x.scenario_id for x in report.failures()} == {"false", "boom"}


def test_certification_refuses_missing_evidence():
    arena = AutonomyArena()
    scenarios = baseline_scenarios(
        restart_probe=lambda: True,
        duplicate_event_probe=lambda: True,
        provider_failover_probe=lambda: True,
        unsafe_action_probe=lambda: True,
    )
    report = arena.run(scenarios[:-1])
    cert = arena.certify(OmegaLevel.L3, scenarios, report)
    assert cert.certified is False
    assert any("missing evidence" in reason for reason in cert.reasons)


def test_l3_requires_fault_domain_diversity():
    arena = AutonomyArena()
    scenarios = (
        ArenaScenario("one", "runtime", 3, OmegaLevel.L1, lambda: True),
        ArenaScenario("two", "runtime", 3, OmegaLevel.L3, lambda: True),
    )
    report = arena.run(scenarios)
    cert = arena.certify(OmegaLevel.L3, scenarios, report)
    assert cert.certified is False
    assert "insufficient fault-domain diversity" in cert.reasons


def test_l4_requires_high_severity_recovery_evidence():
    arena = AutonomyArena()
    scenarios = (
        ArenaScenario("a", "runtime", 3, OmegaLevel.L2, lambda: True),
        ArenaScenario("b", "safety", 3, OmegaLevel.L3, lambda: True),
    )
    report = arena.run(scenarios)
    cert = arena.certify(OmegaLevel.L4, scenarios, report)
    assert cert.certified is False
    assert "no high-severity recovery evidence" in cert.reasons


def test_baseline_can_certify_l3_only_when_all_required_probes_pass():
    arena = AutonomyArena()
    scenarios = baseline_scenarios(
        restart_probe=lambda: True,
        duplicate_event_probe=lambda: True,
        provider_failover_probe=lambda: True,
        unsafe_action_probe=lambda: True,
    )
    report = arena.run(scenarios)
    cert = arena.certify(OmegaLevel.L3, scenarios, report)
    assert cert.certified is True
    assert cert.evidence_count == 4
