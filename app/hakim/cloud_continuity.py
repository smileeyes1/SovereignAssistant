"""Crash-safe cloud continuity primitives for the single HAKIM runtime.

The cloud side is a continuation surface, not a second agent. This module protects
the same SQLite state/queue used by HAKIM with verified snapshots and fail-closed
recovery. It intentionally has no network transport and creates no remote shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3

from .durable_state import DurableStateStore


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot: Path
    manifest: Path
    digest: str
    created_at: str


@dataclass(frozen=True)
class PrepareResult:
    status: str
    database_healthy: bool
    restored_from: str | None


class CloudContinuityVault:
    """Verified SQLite snapshots with newest-valid fallback and atomic restore."""

    FORMAT_VERSION = 1

    def __init__(self, database_path: str | Path, snapshot_dir: str | Path, *, retention: int = 8):
        if retention < 2:
            raise ValueError("retention must be at least 2")
        self.database_path = Path(database_path)
        self.snapshot_dir = Path(snapshot_dir)
        self.retention = retention

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _integrity_ok(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True, timeout=10) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, object]) -> None:
        temp = path.with_name(path.name + ".tmp")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        with temp.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        CloudContinuityVault._fsync_directory(path.parent)

    def verify_database(self) -> bool:
        return self._integrity_ok(self.database_path)

    def _snapshot_name(self, now: datetime) -> str:
        return f"omega-{now.strftime('%Y%m%dT%H%M%S%fZ')}.db"

    def create_snapshot(self) -> SnapshotRecord:
        """Create a transactionally consistent standalone SQLite snapshot."""
        if not self.verify_database():
            raise RuntimeError("refusing to snapshot missing or corrupt database")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        now = self._now()
        snapshot = self.snapshot_dir / self._snapshot_name(now)
        temp = snapshot.with_name(snapshot.name + ".tmp")

        source_uri = f"file:{self.database_path.resolve().as_posix()}?mode=ro"
        source = sqlite3.connect(source_uri, uri=True, timeout=30)
        target = sqlite3.connect(temp, timeout=30)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()

        if not self._integrity_ok(temp):
            temp.unlink(missing_ok=True)
            raise RuntimeError("snapshot integrity verification failed")
        with temp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp, snapshot)
        self._fsync_directory(self.snapshot_dir)

        digest = self._digest(snapshot)
        manifest = snapshot.with_suffix(".json")
        self._atomic_json(manifest, {
            "format_version": self.FORMAT_VERSION,
            "snapshot": snapshot.name,
            "sha256": digest,
            "created_at": now.isoformat(),
        })
        self._prune()
        return SnapshotRecord(snapshot, manifest, digest, now.isoformat())

    def _manifest_paths(self) -> list[Path]:
        if not self.snapshot_dir.is_dir():
            return []
        return sorted(self.snapshot_dir.glob("omega-*.json"), key=lambda item: item.name, reverse=True)

    def _read_valid_record(self, manifest: Path) -> SnapshotRecord | None:
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
            if value.get("format_version") != self.FORMAT_VERSION:
                return None
            raw_name = value.get("snapshot")
            digest = value.get("sha256")
            created_at = value.get("created_at")
            if not all(isinstance(item, str) and item for item in (raw_name, digest, created_at)):
                return None
            if Path(raw_name).name != raw_name:
                return None
            snapshot = self.snapshot_dir / raw_name
            if not snapshot.is_file() or self._digest(snapshot) != digest or not self._integrity_ok(snapshot):
                return None
            return SnapshotRecord(snapshot, manifest, digest, created_at)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def valid_snapshots(self) -> list[SnapshotRecord]:
        records: list[SnapshotRecord] = []
        for manifest in self._manifest_paths():
            record = self._read_valid_record(manifest)
            if record is not None:
                records.append(record)
        return records

    def _remove_sidecars(self) -> None:
        for suffix in ("-wal", "-shm"):
            Path(str(self.database_path) + suffix).unlink(missing_ok=True)

    def restore_latest(self) -> SnapshotRecord | None:
        """Restore newest verified snapshot, skipping any corrupt newer snapshot."""
        for record in self.valid_snapshots():
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.database_path.with_name(self.database_path.name + ".restore.tmp")
            shutil.copy2(record.snapshot, temp)
            if not self._integrity_ok(temp):
                temp.unlink(missing_ok=True)
                continue
            with temp.open("rb") as handle:
                os.fsync(handle.fileno())
            self._remove_sidecars()
            os.replace(temp, self.database_path)
            self._fsync_directory(self.database_path.parent)
            if self.verify_database():
                return record
        return None

    def prepare(self) -> PrepareResult:
        """Validate current state; recover only when the current DB is absent/corrupt."""
        if self.verify_database():
            return PrepareResult("healthy", True, None)
        record = self.restore_latest()
        if record is not None:
            return PrepareResult("restored", True, record.snapshot.name)
        if not self.database_path.exists():
            return PrepareResult("fresh", True, None)
        raise RuntimeError("cloud continuity blocked: corrupt DB and no valid snapshot")

    def _prune(self) -> None:
        for manifest in self._manifest_paths()[self.retention:]:
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
                raw_name = value.get("snapshot")
                if isinstance(raw_name, str) and Path(raw_name).name == raw_name:
                    (self.snapshot_dir / raw_name).unlink(missing_ok=True)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            manifest.unlink(missing_ok=True)


class CloudContinuitySupervisor:
    """Lifecycle marker around the verified vault for the single cloud runner."""

    STATE_KEY = "omega.cloud_continuity"

    def __init__(self, vault: CloudContinuityVault):
        self.vault = vault

    def _mark(self, phase: str, *, run_id: str, detail: str) -> None:
        store = DurableStateStore(self.vault.database_path)
        previous = store.get_state(self.STATE_KEY, {})
        generation = 0
        if isinstance(previous, dict):
            try:
                generation = int(previous.get("generation", 0))
            except (TypeError, ValueError):
                generation = 0
        store.set_state(self.STATE_KEY, {
            "generation": generation + 1,
            "phase": phase,
            "run_id": run_id,
            "detail": detail,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "architecture": "single-hakim-local-first-cloud-continuous",
            "phone_public_ingress": False,
        })

    def prepare(self, *, run_id: str) -> PrepareResult:
        result = self.vault.prepare()
        self._mark("prepared", run_id=run_id, detail=f"{result.status}:{result.restored_from or '-'}")
        return result

    def seal(self, *, run_id: str) -> SnapshotRecord:
        if not self.vault.verify_database():
            raise RuntimeError("cloud continuity seal blocked: database integrity failed")
        self._mark("sealed", run_id=run_id, detail="pre-snapshot")
        return self.vault.create_snapshot()

    def status(self) -> dict[str, object]:
        return {
            "database_exists": self.vault.database_path.is_file(),
            "database_healthy": self.vault.verify_database(),
            "valid_snapshots": len(self.vault.valid_snapshots()),
        }
