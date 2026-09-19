from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.hakim.mission_autonomy import CandidateScore
from app.hakim.mission_kernel import AuthorityLevel
from app.hakim.system_factory import BoundedSystemFactory, FactoryPolicy, SystemGap, SystemSpec


def make_factory(tmp):
    owned = Path(tmp) / "owned"
    owned.mkdir()
    return BoundedSystemFactory(Path(tmp) / "factory", FactoryPolicy((owned,))), owned


def test_gap_plans_builds_and_promotes_trusted_file_monitor():
    with TemporaryDirectory() as tmp:
        factory, owned = make_factory(tmp)
        target = owned / "state.json"
        target.write_text("{}")
        gap = SystemGap(
            "loop_state_freshness",
            "detect silent staleness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("state-file-present",),
            {"path": str(target), "max_age_seconds": 120},
        )
        spec = factory.plan_gap(gap)
        built = factory.build(spec)
        result = factory.qualify_and_promote(
            built,
            challenger=CandidateScore("challenger", 0.9, 1.0, True),
            champion=None,
            probe=lambda item: item.sha256 == built.sha256,
        )
        assert result.promoted
        assert factory.current(spec.name).sha256 == built.sha256
        assert result.manifest["artifact_sha256"] == built.sha256
        assert result.manifest["policy_sha256"] == factory.policy.digest()
        assert result.manifest["canary"] == "passed"


def test_external_path_is_rejected_by_owned_resource_policy():
    with TemporaryDirectory() as tmp:
        factory, _ = make_factory(tmp)
        spec = SystemSpec(
            "outside_path",
            "file_freshness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("claim",),
            {"path": "/etc/passwd", "max_age_seconds": 60},
        )
        ok, reason = factory.validate(spec)
        assert not ok
        assert "owned roots" in reason


def test_nonlocal_http_probe_is_rejected():
    with TemporaryDirectory() as tmp:
        factory, _ = make_factory(tmp)
        spec = SystemSpec(
            "external_probe",
            "local_http_probe",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("claim",),
            {"url": "http://example.com:8080/health", "expected": "ok"},
        )
        ok, reason = factory.validate(spec)
        assert not ok
        assert "localhost" in reason


def test_consequential_factory_action_keeps_human_authority_gate():
    with TemporaryDirectory() as tmp:
        factory, owned = make_factory(tmp)
        target = owned / "state"
        target.write_text("ok")
        spec = SystemSpec(
            "consequential_change",
            "file_freshness",
            "system-factory",
            2,
            True,
            AuthorityLevel.CONSEQUENTIAL,
            ("approved-plan",),
            {"path": str(target), "max_age_seconds": 60},
        )
        ok, reason = factory.validate(spec)
        assert not ok
        assert "human authority gate" in reason
        ok, _ = factory.validate(spec, human_approved=True)
        assert ok


def test_failed_canary_never_replaces_champion():
    with TemporaryDirectory() as tmp:
        factory, owned = make_factory(tmp)
        target = owned / "state"
        target.write_text("ok")
        champion_spec = SystemSpec(
            "health_guard",
            "file_freshness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("baseline",),
            {"path": str(target), "max_age_seconds": 120},
        )
        champion = factory.build(champion_spec)
        assert factory.qualify_and_promote(
            champion,
            challenger=CandidateScore("v1", 0.8, 1.0, True),
            champion=None,
            probe=lambda _: True,
        ).promoted

        challenger_spec = SystemSpec(
            "health_guard",
            "file_freshness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("improvement",),
            {"path": str(target), "max_age_seconds": 30},
        )
        challenger = factory.build(challenger_spec)
        result = factory.qualify_and_promote(
            challenger,
            challenger=CandidateScore("v2", 0.9, 1.0, True),
            champion=CandidateScore("v1", 0.8, 1.0, True),
            probe=lambda _: False,
        )
        assert not result.promoted
        assert result.selected == "champion"
        assert factory.current("health_guard").sha256 == champion.sha256


def test_runtime_failure_rolls_back_to_previous_champion():
    with TemporaryDirectory() as tmp:
        factory, owned = make_factory(tmp)
        target = owned / "state"
        target.write_text("ok")

        v1 = factory.build(SystemSpec(
            "rollback_guard",
            "file_freshness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("v1",),
            {"path": str(target), "max_age_seconds": 120},
        ))
        assert factory.qualify_and_promote(
            v1,
            challenger=CandidateScore("v1", 0.8, 1.0, True),
            champion=None,
            probe=lambda _: True,
        ).promoted

        v2 = factory.build(SystemSpec(
            "rollback_guard",
            "file_freshness",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("v2",),
            {"path": str(target), "max_age_seconds": 60},
        ))
        assert factory.qualify_and_promote(
            v2,
            challenger=CandidateScore("v2", 0.9, 1.0, True),
            champion=CandidateScore("v1", 0.8, 1.0, True),
            probe=lambda _: True,
        ).promoted
        assert factory.current("rollback_guard").sha256 == v2.sha256

        assert factory.rollback("rollback_guard", failing_probe=lambda _: False)
        assert factory.current("rollback_guard").sha256 == v1.sha256
        assert (Path(tmp) / "factory" / "rollback_guard" / "failed.json").exists()


def test_unknown_gap_fails_closed_instead_of_generating_free_code():
    with TemporaryDirectory() as tmp:
        factory, _ = make_factory(tmp)
        gap = SystemGap(
            "novel_unknown",
            "do arbitrary new thing",
            "system-factory",
            1,
            True,
            AuthorityLevel.REVERSIBLE,
            ("need",),
            {"shell": "echo unsafe"},
        )
        with pytest.raises(ValueError):
            factory.plan_gap(gap)
