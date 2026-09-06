import json
import sqlite3

import pytest

from app.hakim.local_sovereign import (
    GuardedWorkspace,
    LocalAgentLoop,
    LocalModelClient,
    LocalSovereignConfig,
    LocalSovereignRuntime,
    LocalSovereignStore,
    VerifiedBackupManager,
)


def test_idempotent_queue_and_priority(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    a = s.enqueue_goal("goal", priority=10)
    b = s.enqueue_goal("goal", priority=10)
    assert a == b
    c = s.enqueue_goal("urgent", priority=90)
    assert s.claim_next("w").job_id == c


def test_unverified_checkpoint_cannot_replace_lkg(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    old = s.create_checkpoint({"v": 1}); s.verify_checkpoint(old); s.promote_checkpoint(old)
    candidate = s.create_checkpoint({"v": 2})
    with pytest.raises(RuntimeError): s.promote_checkpoint(candidate)
    assert s.last_verified_checkpoint() == {"v": 1}
    s.verify_checkpoint(candidate); s.promote_checkpoint(candidate)
    assert s.last_verified_checkpoint() == {"v": 2}


def test_backup_is_verified_and_restore_is_non_destructive(tmp_path):
    rt = LocalSovereignRuntime(LocalSovereignConfig(tmp_path / "work"))
    rt.store.set("x", {"a": 1})
    backup = rt.backups.create(label="test")
    assert VerifiedBackupManager.verify(backup)
    restored = VerifiedBackupManager.restore(backup, tmp_path / "restore")
    with sqlite3.connect(restored) as conn:
        assert conn.execute("select count(*) from kv_state").fetchone()[0] == 1
    with pytest.raises(FileExistsError): VerifiedBackupManager.restore(backup, tmp_path / "restore")


def test_local_model_rejects_remote_endpoint_by_default():
    with pytest.raises(ValueError):
        LocalModelClient("m", base_url="https://example.com/v1")


def test_workspace_blocks_path_escape_and_shell_commands(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    w = GuardedWorkspace(tmp_path / "work", s)
    with pytest.raises(ValueError): w.write_text("../escape.txt", "x")
    with pytest.raises(PermissionError): w.run_process(["sh", "-c", "echo nope"])


def test_workspace_write_read_search_and_hash(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    w = GuardedWorkspace(tmp_path / "work", s)
    info = w.write_text("docs/a.txt", "مرحبا sovereign")
    assert len(info["sha256"]) == 64
    assert w.read_text("docs/a.txt") == "مرحبا sovereign"
    assert w.search_text("sovereign")[0]["path"] == "docs/a.txt"


class FakeResponse:
    status = 200
    def __init__(self, body): self.body = body
    def read(self): return json.dumps(self.body).encode()


def test_local_model_health_and_chat_with_loopback_fake():
    calls = []
    def opener(req, timeout=0):
        calls.append(req.full_url)
        if req.full_url.endswith("/models"): return FakeResponse({"data": []})
        return FakeResponse({"choices":[{"message":{"content":"{\"action\":\"final\",\"status\":\"PASS\",\"message\":\"ok\"}"}}]})
    m = LocalModelClient("m", opener=opener)
    assert m.health()
    assert "PASS" in m.chat([{"role":"user","content":"x"}])


def test_agent_loop_executes_local_tool_then_finishes(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    w = GuardedWorkspace(tmp_path / "work", s)
    outputs = iter([
        '{"action":"tool","tool":"write_text","args":{"path":"x.txt","content":"hello"},"reason":"create"}',
        '{"action":"final","status":"PASS","message":"done"}',
    ])
    class Model:
        def chat(self, messages, **kwargs): return next(outputs)
    loop = LocalAgentLoop(s, w, Model())
    result = loop.run_goal("create x")
    assert result["status"] == "PASS"
    assert (tmp_path / "work" / "x.txt").read_text() == "hello"


def test_process_once_is_restart_safe(tmp_path):
    s = LocalSovereignStore(tmp_path / "state.db")
    w = GuardedWorkspace(tmp_path / "work", s)
    job = s.enqueue_goal("finish")
    class Model:
        def chat(self, messages, **kwargs):
            return '{"action":"final","status":"PASS","message":"done"}'
    loop = LocalAgentLoop(s, w, Model())
    assert loop.process_once() == "PASS"
    assert s.get_job(job)["status"] == "completed"
