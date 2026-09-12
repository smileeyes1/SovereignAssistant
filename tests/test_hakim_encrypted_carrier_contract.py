from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
RELAY = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt"
POLICY = ROOT / "governance/HAKIM_BRIDGE_POLICY_v2.json"


def test_android_remote_carrier_is_ciphertext_only_and_fail_closed():
    t = RELAY.read_text(encoding="utf-8")
    assert 'private const val CARRIER_PREFIX = "HC1."' in t
    assert 'private const val CARRIER_AAD = "HAKIM-CARRIER-v1"' in t
    assert 'private const val GCM_NONCE_BYTES = 12' in t
    assert 'private const val GCM_TAG_BITS = 128' in t
    assert 'if (!carrier.startsWith(CARRIER_PREFIX)) return null' in t
    assert 'val raw = decryptCarrier(carrier, relayKey) ?: return' in t
    assert 'Cipher.getInstance("AES/GCM/NoPadding")' in t
    assert 'GCMParameterSpec(GCM_TAG_BITS, nonce)' in t
    assert 'cipher.updateAAD(CARRIER_AAD.toByteArray(Charsets.UTF_8))' in t
    # The old public-carrier plaintext decode path must not return.
    assert 'String(Base64.decode(encoded,' not in t


def test_carrier_key_is_domain_separated_from_hmac_use():
    t = RELAY.read_text(encoding="utf-8")
    assert 'val keyMaterial = "$CARRIER_AAD\\u0000$relayKey"' in t
    assert 'MessageDigest.getInstance("SHA-256").digest(keyMaterial)' in t
    assert 'Mac.getInstance("HmacSHA256")' in t


def test_bridge_policy_requires_ciphertext_only_public_carrier():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    s = p["security"]
    assert s["carrier_protocol"] == "HC1"
    assert s["carrier_content_encryption"] == "AES-256-GCM"
    assert s["public_carrier_payload"] == "CIPHERTEXT_ONLY"
    assert s["signed_commands"] is True
    assert s["anti_replay"] is True
