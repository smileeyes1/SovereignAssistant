from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_zero_cost_transport_has_no_make_webhook_dependency():
    relay = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt")
    activity = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/MainActivity.kt")
    assert "relay_result_url" not in relay
    assert "hook.eu1.make.com" not in relay
    assert 'const val KEY_RESULT_TOPIC = "relay_result_topic"' in relay
    assert 'const val KEY_RELAY_BASE = "relay_base_url"' in relay
    assert 'private const val DEFAULT_RELAY_BASE = "https://ntfy.sh"' in relay
    assert 'uri.getQueryParameter("result_topic")' in activity
    assert 'uri.getQueryParameter("relay_base")' in activity


def test_commands_and_results_are_both_encrypted():
    relay = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt")
    assert 'private const val CARRIER_PREFIX = "HC1."' in relay
    assert 'private const val RESULT_PREFIX = "HR1."' in relay
    assert 'private const val CARRIER_AAD = "HAKIM-CARRIER-v1"' in relay
    assert 'private const val RESULT_AAD = "HAKIM-RESULT-v1"' in relay
    assert "AES/GCM/NoPadding" in relay
    assert "HmacSHA256" in relay
    assert "encryptResult" in relay
    assert 'conn.setRequestProperty("Content-Type", "text/plain; charset=utf-8")' in relay


def test_relay_is_replaceable_and_https_only():
    relay = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt")
    assert "validRelayBase" in relay
    assert 'Regex("^https://' in relay
    assert 'URL("$relayBase/$topic/json?poll=1&since=$since")' in relay
    assert 'URL("$relayBase/$resultTopic")' in relay


def test_state_changing_remote_ops_still_require_explicit_approval():
    relay = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimRemoteRelay.kt")
    assert 'private val READ_ONLY_OPS = setOf("status", "ui", "notifications", "screenshot")' in relay
    assert 'private val ALLOWED_OPS = READ_ONLY_OPS + setOf("action", "launch")' in relay
    assert "showApproval(context, requestId, op)" in relay
    assert '"موافقة"' in relay
    assert '"رفض"' in relay


def test_version_is_higher_than_relay_recovery_release():
    gradle = text("android/hakim-companion/app/build.gradle.kts")
    assert "versionCode = 4" in gradle
    assert 'versionName = "0.3.0-zero-cost-independent"' in gradle
