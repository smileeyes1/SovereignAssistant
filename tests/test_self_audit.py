from app.hakim.capability_registry import CapabilityRegistry
from app.hakim.goal_governor import Goal, GoalPortfolio, GoalStatus
from app.hakim.production import ProductionConfig, build_production_runtime
from app.hakim.self_audit import AutonomySelfAuditor


def runtime(tmp_path, *, allow_file_write=False):
    cfg = ProductionConfig(
        database_path=tmp_path / "omega.db",
        worker_id="w",
        repository="o/r",
        github_token="t",
        github_webhook_secret="s",
        runtime_token="r",
        host="127.0.0.1",
        port=0,
        allow_file_write=allow_file_write,
    )
    return build_production_runtime(cfg)


def test_dead_letter_is_detected_and_persisted_as_blocker(tmp_path):
    rt = runtime(tmp_path)
    rt.queue.enqueue("dead-1", "manual_signal", "x", {}, max_attempts=1)
    item = rt.queue.claim("w")
    assert item is not None
    assert rt.queue.fail("dead-1", "w", "boom") == "dead"
    report = AutonomySelfAuditor(rt).run_once(force=True)
    assert report.status == "blocked"
    assert any("dead work dead-1" in blocker for blocker in report.blockers)
    saved = rt.state.get_state("omega.self_audit.last")
    assert saved["dead_work_count"] == 1


def test_idle_ready_roadmap_emits_durable_recovery_event_when_coding_is_available(tmp_path):
    rt = runtime(tmp_path, allow_file_write=True)
    GoalPortfolio(rt).save_all([Goal("next", "Next", "continue roadmap", 10)])
    report = AutonomySelfAuditor(rt).run_once(force=True)
    assert report.status == "recovery_enqueued"
    assert report.recovery_event == "omega-self-audit-continue-next"
    queued = rt.queue.get(report.recovery_event)
    assert queued is not None
    assert queued.status == "pending"


def test_unfinished_mission_without_coding_capability_is_not_silent_idle(tmp_path):
    rt = runtime(tmp_path, allow_file_write=False)
    GoalPortfolio(rt).save_all([Goal("next", "Next", "continue roadmap", 10)])
    report = AutonomySelfAuditor(rt).run_once(force=True)
    assert report.status == "blocked"
    assert report.recovery_event is None
    assert any("mission incomplete" in blocker and "next" in blocker for blocker in report.blockers)
    saved = rt.state.get_state("omega.self_audit.last")
    assert saved["mission_complete"] is False
    assert saved["next_ready_goal"] == "next"


def test_exhausted_repair_budget_blocks_silent_loop(tmp_path):
    rt = runtime(tmp_path)
    GoalPortfolio(rt).save_all([
        Goal("g", "G", "repair", 10, status=GoalStatus.VERIFYING, pr_number=7, head_sha="sha")
    ])
    rt.state.set_state("omega.ci_repair.pr.7.attempts", 3)
    report = AutonomySelfAuditor(rt, repair_budget=3).run_once(force=True)
    assert report.status == "blocked"
    assert any("repair budget exhausted" in blocker for blocker in report.blockers)


def test_unhealthy_required_provider_is_explicit_blocker(tmp_path):
    rt = runtime(tmp_path, allow_file_write=True)
    capabilities = CapabilityRegistry(rt.state, failure_threshold=1)
    capabilities.record_failure("openai-responses", "provider unavailable")
    report = AutonomySelfAuditor(rt, capabilities).run_once(force=True)
    assert report.status == "blocked"
    assert any("openai-responses unhealthy" in blocker for blocker in report.blockers)
