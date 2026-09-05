from app.hakim.capability_registry import CapabilityRegistry
from app.hakim.coding_provider import CodingProviderPool, PatchPlan, PatchRequest
from app.hakim.durable_state import DurableStateStore


class Provider:
    def __init__(self, name, outcomes):
        self.name = name
        self.outcomes = list(outcomes)
        self.calls = 0

    def propose_patch(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return PatchPlan(self.name, "ok", {"app/x.py": "X = 1\n"})


def request():
    return PatchRequest("objective", "", {})


def test_health_survives_restart_and_excludes_unhealthy_provider(tmp_path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    registry = CapabilityRegistry(state, failure_threshold=2)
    primary = Provider("primary", [RuntimeError("down"), RuntimeError("down")])
    backup = Provider("backup", [True, True, True])
    pool = CodingProviderPool([primary, backup], registry)

    assert pool.propose_patch(request()).provider == "backup"
    assert pool.propose_patch(request()).provider == "backup"
    assert registry.get("primary").healthy is False

    restarted = CapabilityRegistry(DurableStateStore(db), failure_threshold=2)
    primary_after = Provider("primary", [True])
    backup_after = Provider("backup", [True])
    restarted_pool = CodingProviderPool([primary_after, backup_after], restarted)
    assert restarted_pool.propose_patch(request()).provider == "backup"
    assert primary_after.calls == 0


def test_healthy_signal_restores_provider_selection(tmp_path):
    registry = CapabilityRegistry(DurableStateStore(tmp_path / "omega.db"), failure_threshold=1)
    registry.record_failure("primary", "temporary outage")
    assert registry.is_healthy("primary") is False
    registry.record_success("primary")
    assert registry.is_healthy("primary") is True
    primary = Provider("primary", [True])
    backup = Provider("backup", [True])
    pool = CodingProviderPool([primary, backup], registry)
    assert pool.propose_patch(request()).provider == "primary"
    assert primary.calls == 1
    assert backup.calls == 0


def test_all_unhealthy_fails_closed_without_calling_provider(tmp_path):
    registry = CapabilityRegistry(DurableStateStore(tmp_path / "omega.db"), failure_threshold=1)
    registry.record_failure("only", "down")
    provider = Provider("only", [True])
    pool = CodingProviderPool([provider], registry)
    try:
        pool.propose_patch(request())
        assert False, "expected no healthy provider failure"
    except RuntimeError as exc:
        assert "healthy coding providers available" in str(exc)
    assert provider.calls == 0
