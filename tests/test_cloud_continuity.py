from __future__ import annotations

import json

import pytest

from app.hakim.cloud_continuity import CloudContinuitySupervisor, CloudContinuityVault
from app.hakim.durable_state import DurableStateStore
from app.hakim.durable_worker import DurableWorkQueue


def test_snapshot_round_trip_preserves_state_and_pending_work(tmp_path):
    db = tmp_path / "omega.db"
    snapshots = tmp_path / "snapshots"
    state = DurableStateStore(db)
    queue = DurableWorkQueue(db)
    state.set_state("mission", {"checkpoint": "safe-1"})
    assert queue.enqueue("job-1", "manual_signal", "resume", {"n": 1})

    vault = CloudContinuityVault(db, snapshots)
    first = vault.create_snapshot()

    state.set_state("mission", {"checkpoint": "later"})
    assert vault.restore_latest() == first

    reopened = DurableStateStore(db)
    reopened_queue = DurableWorkQueue(db)
    assert reopened.get_state("mission") == {"checkpoint": "safe-1"}
    assert reopened_queue.get("job-1").status == "pending"


def test_corrupt_newest_snapshot_falls_back_to_previous_valid_snapshot(tmp_path):
    db = tmp_path / "omega.db"
    snapshots = tmp_path / "snapshots"
    state = DurableStateStore(db)
    vault = CloudContinuityVault(db, snapshots)

    state.set_state("generation", 1)
    old = vault.create_snapshot()
    state.set_state("generation", 2)
    newest = vault.create_snapshot()

    newest.snapshot.write_bytes(b"not-a-sqlite-database")
    db.write_bytes(b"broken-live-db")

    restored = vault.restore_latest()
    assert restored is not None
    assert restored.snapshot.name == old.snapshot.name
    assert DurableStateStore(db).get_state("generation") == 1


def test_corrupt_live_database_without_valid_snapshot_fails_closed(tmp_path):
    db = tmp_path / "omega.db"
    db.write_bytes(b"broken")
    vault = CloudContinuityVault(db, tmp_path / "snapshots")
    with pytest.raises(RuntimeError, match="corrupt DB"):
        vault.prepare()


def test_prepare_fresh_then_seal_creates_verified_recovery_point(tmp_path):
    db = tmp_path / "omega.db"
    vault = CloudContinuityVault(db, tmp_path / "snapshots")
    supervisor = CloudContinuitySupervisor(vault)

    result = supervisor.prepare(run_id="run:1")
    assert result.status == "fresh"
    assert vault.verify_database()

    record = supervisor.seal(run_id="run:1")
    assert record.snapshot.is_file()
    assert vault.valid_snapshots()[0].digest == record.digest

    state = DurableStateStore(db).get_state("omega.cloud_continuity")
    assert state["phase"] == "sealed"
    assert state["architecture"] == "single-hakim-local-first-cloud-continuous"
    assert state["phone_public_ingress"] is False


def test_retention_keeps_multiple_rollback_points_but_is_bounded(tmp_path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    vault = CloudContinuityVault(db, tmp_path / "snapshots", retention=3)

    for value in range(5):
        state.set_state("n", value)
        vault.create_snapshot()

    manifests = list((tmp_path / "snapshots").glob("omega-*.json"))
    databases = list((tmp_path / "snapshots").glob("omega-*.db"))
    assert len(manifests) == 3
    assert len(databases) == 3


def test_manifest_path_traversal_is_rejected(tmp_path):
    db = tmp_path / "omega.db"
    state = DurableStateStore(db)
    state.set_state("ok", True)
    vault = CloudContinuityVault(db, tmp_path / "snapshots")
    record = vault.create_snapshot()

    payload = json.loads(record.manifest.read_text(encoding="utf-8"))
    payload["snapshot"] = "../escape.db"
    record.manifest.write_text(json.dumps(payload), encoding="utf-8")

    assert vault.valid_snapshots() == []
