from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "android-physical-field-gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("android_physical_field_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_token_file_requires_private_permissions(tmp_path):
    gate = load_gate()
    token = tmp_path / "companion.token"
    token.write_text("a" * 48, encoding="utf-8")
    token.chmod(0o600)
    value, checks = gate.check_token_file(token)
    assert value == "a" * 48
    assert [c.status for c in checks] == ["PASS", "PASS"]

    token.chmod(0o644)
    _, checks = gate.check_token_file(token)
    assert checks[-1].status == "FAIL"


def test_local_status_proves_loopback_and_rejects_wrong_token(monkeypatch):
    gate = load_gate()
    good = "good-token-" + "x" * 38

    def fake_json_request(url, *, token=None, timeout=5.0):
        assert url == gate.STATUS_URL
        if token == good:
            return 200, {
                "evidence_state": "NOT_PROVEN",
                "loopback_only": True,
                "control_server_listening": True,
                "persistent_model_allowed": False,
            }
        return 401, {"error": "unauthorized"}

    monkeypatch.setattr(gate, "json_request", fake_json_request)
    payload, checks = gate.check_local_status(good)
    assert payload is not None
    assert all(c.status == "PASS" for c in checks)


def test_latest_release_requires_manifest_and_digest_match(monkeypatch):
    gate = load_gate()
    sha = "1" * 40
    apk_sha = "a" * 64
    release = {
        "tag_name": "hakim-companion-test",
        "target_commitish": sha,
        "assets": [
            {
                "name": "hakim-companion-unsigned.apk",
                "digest": f"sha256:{apk_sha}",
                "browser_download_url": "https://example.invalid/app.apk",
            },
            {
                "name": "hakim-companion-unsigned.apk.sha256",
                "browser_download_url": "https://example.invalid/app.sha256",
            },
            {
                "name": "hakim-companion-build-manifest.json",
                "browser_download_url": "https://example.invalid/manifest.json",
            },
        ],
    }
    manifest = {
        "source_commit_sha": sha,
        "apk_sha256": apk_sha,
        "android_tree_sha": "b" * 40,
        "field_verification": "NOT_PROVEN_BY_BUILD",
    }

    monkeypatch.setattr(gate, "json_request", lambda *a, **k: (200, release))
    monkeypatch.setattr(
        gate,
        "text_request",
        lambda *a, **k: (200, json.dumps(manifest)),
    )
    data, checks = gate.latest_release()
    assert data is not None
    assert all(c.status == "PASS" for c in checks)


def test_gate_is_fail_closed_and_never_self_promotes_field_verification():
    gate = load_gate()
    assert gate.summarize([gate.Check("x", "PASS")]) == "PRE_FIELD_PASS"
    assert gate.summarize([gate.Check("x", "FAIL")]) == "FAIL"
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"field_verified": False' in text
    assert '"promotion_allowed": False' in text
    assert "FIELD_VERIFIED" in text
    assert "secrets_recorded" in text
    assert '"token": token' not in text
