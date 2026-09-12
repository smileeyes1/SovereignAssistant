from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
TASK = APP / "HakimSignedTask.kt"
POLICY = ROOT / "governance/HAKIM_BRIDGE_POLICY_v2.json"


def test_external_carrier_sources_are_removed_from_sovereign_local_runtime():
    assert not (APP / "HakimRemoteRelay.kt").exists()
    assert not (APP / "HakimDirectRelay.kt").exists()
    runtime = "\n".join(p.read_text(encoding="utf-8") for p in APP.glob("*.kt"))
    assert "ntfy.sh" not in runtime
    assert "HC1." not in runtime
    assert "RESULT_PREFIX" not in runtime


def test_signed_local_task_uses_domain_separated_hmac_and_fail_closed_checks():
    t = TASK.read_text(encoding="utf-8")
    assert 'private const val AAD = "HAKIM-TASK-v1"' in t
    assert 'Mac.getInstance("HmacSHA256")' in t
    assert 'SecretKeySpec(token.toByteArray(Charsets.UTF_8), "HmacSHA256")' in t
    assert 'MessageDigest.isEqual' in t
    assert 'task_bad_signature' in t
    assert 'task_duplicate' in t
    assert 'task_expired_or_too_far' in t
    assert 'MAX_FUTURE_MS' in t
    assert 'ALLOWED_ACTIONS' in t


def test_bridge_policy_forbids_public_and_background_carriers():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    s = p["security"]
    assert p["public_command_transport"] is False
    assert p["public_ciphertext_carrier_allowed"] is False
    assert p["external_background_command_transport"] == "DISABLED"
    assert s["loopback_only_control_plane"] is True
    assert s["signed_local_task_deep_link"] is True
    assert s["task_signature"] == "HMAC-SHA256"
    assert s["expiry_required"] is True
    assert s["anti_replay"] is True
    assert s["external_background_transport"] is False
