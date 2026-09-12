from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
TASK = JAVA / "HakimSignedTask.kt"
RELAY = JAVA / "HakimRemoteRelay.kt"
POLICY = ROOT / "governance/HAKIM_BRIDGE_POLICY_v2.json"


def test_sovereign_local_release_has_no_background_remote_carrier_source():
    assert not RELAY.exists()
    runtime_text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in JAVA.rglob("*.kt")
    )
    for forbidden in ("ntfy.sh", "HakimRemoteRelay(", "hook.eu1.make.com", "TinyFish"):
        assert forbidden not in runtime_text


def test_chat_handoff_uses_domain_separated_hmac_signed_expiring_local_task():
    t = TASK.read_text(encoding="utf-8")
    assert 'private const val AAD = "HAKIM-TASK-v1"' in t
    assert 'Mac.getInstance("HmacSHA256")' in t
    assert 'SecretKeySpec(token.toByteArray(Charsets.UTF_8), "HmacSHA256")' in t
    assert 'MessageDigest.isEqual' in t
    assert 'private const val MAX_FUTURE_MS' in t
    assert 'task_expired_or_too_far' in t
    assert 'task_duplicate' in t
    assert 'getSharedPreferences("hakim_signed_task_ids"' in t


def test_bridge_policy_forbids_hidden_public_or_vendor_carrier_core():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert p["core"]["background_external_transport"] == "NONE"
    assert p["core"]["chat_to_phone_handoff"] == "USER_OPENED_SIGNED_EXPIRING_REPLAY_PROTECTED_TASK_LINK"
    assert p["public_command_transport"] is False
    assert p["public_github_command_relay"] == "DISABLED"
    assert p["fallback_command_transport"] == "NONE_BY_DEFAULT"
    forbidden = p["runtime_forbidden_as_hidden_core"]
    for marker in ("MAKE", "TINYFISH", "NTFY", "PAID_API", "PAID_OPERATION_CREDIT", "PUBLIC_GITHUB_COMMAND_RELAY"):
        assert marker in forbidden
    assert p["security"]["signed_tasks"] is True
    assert p["security"]["anti_replay"] is True
