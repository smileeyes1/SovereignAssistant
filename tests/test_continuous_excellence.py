from pathlib import Path

from app.hakim.continuous_excellence import ContinuousExcellenceController, ImprovementSignal
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


def test_enqueued_improvement_requires_guarded_release_stages(tmp_path: Path):
    db = tmp_path / "omega.db"
    queue = DurableWorkQueue(db)
    controller = ContinuousExcellenceController(DurableStateStore(db), queue)
    decision = controller.evaluate((ImprovementSignal("quality", "raise verified quality", 4, ("benchmark:regression",)),))
    item = queue.get(decision.event_id)
    assert item is not None
    assert item.payload["requires_sandbox"] is True
    assert item.payload["requires_benchmark"] is True
    assert item.payload["requires_canary"] is True
