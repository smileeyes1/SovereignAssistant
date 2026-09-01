from pathlib import Path
import urllib.request
import pytest

from app.hakim.r1 import ProjectStore, LocalRuntime, PreviewServer, ContinuationEngine, ContinuationStep


def test_project_store_blocks_escape(tmp_path):
    store = ProjectStore(tmp_path)
    store.write_text("p1", "index.html", "ok")
    assert store.snapshot("p1")["index.html"] == "ok"
    with pytest.raises(ValueError):
        store.write_text("p1", "../escape.txt", "bad")
    with pytest.raises(ValueError, match="project_id escapes"):
        store.project_path("../outside")
    with pytest.raises(ValueError, match="project_id is required"):
        store.project_path("   ")


def test_local_runtime_executes_and_logs(tmp_path):
    store = ProjectStore(tmp_path)
    runtime = LocalRuntime(store)
    result = runtime.run("p1", ["python", "-c", "print('omega')"])
    assert result.returncode == 0
    assert result.stdout.strip() == "omega"
    assert runtime.logs[-1]["returncode"] == 0


def test_preview_serves_project(tmp_path):
    store = ProjectStore(tmp_path)
    store.write_text("p1", "index.html", "OMEGA-R1")
    handle = PreviewServer().start(store.project_path("p1"))
    try:
        body = urllib.request.urlopen(handle.url, timeout=3).read().decode()
        assert "OMEGA-R1" in body
    finally:
        handle.stop()


def test_continuation_selects_only_safe_reversible_ready_step():
    engine = ContinuationEngine()
    selected = engine.choose([
        ContinuationStep("deploy irreversible", safe=True, reversible=False),
        ContinuationStep("unsafe", safe=False, reversible=True),
        ContinuationStep("next safe", safe=True, reversible=True),
    ])
    assert selected is not None
    assert selected.name == "next safe"
