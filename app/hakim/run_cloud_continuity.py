"""CLI lifecycle hook used by the cloud continuation workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from .cloud_continuity import CloudContinuitySupervisor, CloudContinuityVault


def _runtime() -> tuple[CloudContinuitySupervisor, str]:
    db = Path(os.environ.get("OMEGA_DB_PATH", ".omega/omega.db"))
    snapshot_dir = Path(
        os.environ.get(
            "OMEGA_CONTINUITY_SNAPSHOT_DIR",
            str(db.parent / "cloud-continuity"),
        )
    )
    retention = int(os.environ.get("OMEGA_CONTINUITY_RETENTION", "8"))
    run_id = os.environ.get("GITHUB_RUN_ID", "local") + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    return CloudContinuitySupervisor(
        CloudContinuityVault(db, snapshot_dir, retention=retention)
    ), run_id


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"prepare", "seal", "status"}:
        raise SystemExit("usage: run_cloud_continuity {prepare|seal|status}")

    supervisor, run_id = _runtime()
    command = args[0]
    if command == "prepare":
        result = supervisor.prepare(run_id=run_id)
        payload = {
            "status": result.status,
            "database_healthy": result.database_healthy,
            "restored_from": result.restored_from,
        }
    elif command == "seal":
        record = supervisor.seal(run_id=run_id)
        payload = {
            "status": "sealed",
            "snapshot": record.snapshot.name,
            "sha256": record.digest,
        }
    else:
        payload = supervisor.status()

    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
