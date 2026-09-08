"""Persist a self-describing ΩL7 certification artifact.

This wrapper preserves the existing arena gate and then binds its durable
certificate to the exact supported operational envelope. It fails closed if
the underlying gate does not produce the expected artifact.
"""
from __future__ import annotations

import json
from pathlib import Path

from .autonomy_arena import L7_OPERATIONAL_ENVELOPE
from .run_arena_gate import main as run_arena_gate


CERTIFICATE_PATH = Path(".omega/autonomy-certification.json")


def _envelope_payload() -> dict[str, object]:
    envelope = L7_OPERATIONAL_ENVELOPE
    return {
        "capabilities": sorted(envelope.allowed_capabilities),
        "max_risk": envelope.max_risk,
        "require_reversible_above": envelope.require_reversible_above,
        "min_evidence": envelope.min_evidence,
    }


def main() -> None:
    run_arena_gate()
    if not CERTIFICATE_PATH.is_file():
        raise SystemExit("ΩL7 certification artifact missing after arena gate")

    payload = json.loads(CERTIFICATE_PATH.read_text(encoding="utf-8"))
    if payload.get("requested_level") != "L7" or payload.get("certified") is not True:
        raise SystemExit("refusing to scope an unverified ΩL7 certificate")

    payload["operational_envelope"] = _envelope_payload()
    CERTIFICATE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
