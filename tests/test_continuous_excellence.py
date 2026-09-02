from pathlib import Path

from app.hakim.continuous_excellence import (
    ContinuousExcellenceController,
    ImprovementSignal,
    OperationalSignalCollector,
)
from app.hakim.durable_state import DurableStateStore
from app.hakim.durable_worker import DurableWorkQueue


def test_highest_verified_reversible_gap_is_enqueued_once(tmp_path: Path):
    db = tmp_path / "omega.db"
    controller = ContinuousExcellenceController(DurableStateStore(db), DurableWorkQueue(db))
    low = ImprovementSignal("cost", "reduce waste", 2, ("metric:cost",))
    high = ImprovementSignal("reliability", "remove observed stall", 5, ("metric:stall", "trace:42"))
    first = controller.evaluate((low, high))
    second = controller.evaluate((high, low))
    assert first.status == "improvement_enqueued"
    assert first.selected_domain == "reliability"
    assert second.status == "improvement_already_known"
    assert first.event_id == second.event_id


def test_unverified_or_irreversible_gap_cannot_create_work(tmp_path: Path):
    db = tmp_path / "omega.db"
    controller = ContinuousExcellenceController(DurableStateStore(db), DurableWorkQueue(db))
    decision = controller.evaluate((
        ImprovementSignal("novelty", "change for novelty", 5, ()),
        ImprovementSignal("prod", "irreversible mutation", 5, ("claim",), reversible=False),
    ))
    assert decision.status == "baseline_healthy"
    assert decision.event_id is None


def test_enqueued_improvement_requires_full_guarded_release_cycle(tmp_path: Path):
    db = tmp_path / "omega.db"
    queue = DurableWorkQueue(db)
    controller = ContinuousExcellenceController(DurableStateStore(db), queue)
    decision = controller.evaluate((ImprovementSignal("quality", "raise verified quality", 4, ("benchmark:regression",)),))
    item = queue.get(decision.event_id)
    assert item is not None
    assert item.payload["requires_sandbox"] is True
    assert item.payload["requires_benchmark"] is True
    assert item.payload["requires_adversarial_regression"] is True
    assert item.payload["requires_canary"] is True
    assert item.payload["requires_post_promotion_measurement"] is True
    assert item.payload["rollback_on_regression"] is True


def test_collector_discovers_retry_debt_from_durable_runtime_evidence(tmp_path: Path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    queue = DurableWorkQueue(db)
    queue.enqueue("retry-evidence", "manual_signal", "probe", {}, max_attempts=5)
    claimed = queue.claim("worker")
    assert claimed is not None
    queue.fail(claimed.job_id, "worker", "injected transient failure", backoff_seconds=0)
    claimed = queue.claim("worker")
    assert claimed is not None
    queue.complete(claimed.job_id, "worker")
    signals = OperationalSignalCollector(state, queue).collect()
    assert any(s.domain == "reliability" and "recovered_after_retry=1" in s.evidence[0] for s in signals)


def test_explicit_observation_requires_durable_evidence(tmp_path: Path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    queue = DurableWorkQueue(db)
    state.set_state(OperationalSignalCollector.OBSERVATIONS_KEY, [
        {"domain": "quality", "description": "measured regression", "severity": 4, "evidence": ["benchmark:42"], "reversible": True},
        {"domain": "novelty", "description": "unsupported idea", "severity": 5, "evidence": [], "reversible": True},
    ])
    signals = OperationalSignalCollector(state, queue).collect()
    decision = ContinuousExcellenceController(state, queue).evaluate(signals)
    assert decision.status == "improvement_enqueued"
    assert decision.selected_domain == "quality"
