import urllib.request
import pytest

from app.hakim.r1 import ProjectStore
from app.hakim.r2 import AppPlan, IntentToAppEngine, TemplateCodingWorker


def test_intent_to_app_builds_verifies_checkpoints_and_previews(tmp_path):
    engine = IntentToAppEngine(ProjectStore(tmp_path))
    outcome = engine.build("demo", "تطبيق ترحيبي بسيط")
    try:
        assert outcome.verification.passed
        assert outcome.checkpoint.digest
        snapshot = engine.store.snapshot("demo")
        assert "index.html" in snapshot
        assert "تطبيق ترحيبي بسيط" in snapshot["index.html"]
        body = urllib.request.urlopen(outcome.preview.url, timeout=3).read().decode("utf-8")
        assert "Ω Forge" in body
    finally:
        outcome.preview.stop()


class BrokenThenRepairWorker:
    name = "broken-then-repair"

    def build(self, plan: AppPlan):
        return {"index.html": "broken"}

    def repair(self, plan: AppPlan, files, failures):
        return TemplateCodingWorker().build(plan)


def test_repair_loop_recovers_before_completion(tmp_path):
    engine = IntentToAppEngine(ProjectStore(tmp_path), worker=BrokenThenRepairWorker())
    outcome = engine.build("repair", "اصلحني تلقائيا")
    try:
        assert outcome.verification.passed
        assert outcome.repair_attempts == 1
    finally:
        outcome.preview.stop()


class AlwaysBrokenWorker:
    name = "always-broken"

    def build(self, plan: AppPlan):
        return {"index.html": "broken"}

    def repair(self, plan: AppPlan, files, failures):
        return files


def test_failed_verification_is_no_go_and_does_not_write_project(tmp_path):
    store = ProjectStore(tmp_path)
    engine = IntentToAppEngine(store, worker=AlwaysBrokenWorker(), max_repairs=1)
    with pytest.raises(RuntimeError, match="verification failed"):
        engine.build("blocked", "نتيجة يجب التحقق منها")
    assert store.snapshot("blocked") == {}


def test_empty_intent_is_rejected(tmp_path):
    engine = IntentToAppEngine(ProjectStore(tmp_path))
    with pytest.raises(ValueError, match="intent is required"):
        engine.build("demo", "   ")
