from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion"


def text(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_companion_is_loopback_and_token_gated():
    s = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert "InetAddress.getLoopbackAddress()" in s
    assert "Authorization" not in s or 'headers["authorization"]' in s
    assert "Bearer $token" in s
    assert "0.0.0.0" not in s


def test_control_service_is_not_exported_and_accessibility_requires_system_binding():
    m = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'android:name=".HakimForegroundService"' in m
    service_block = m.split('android:name=".HakimForegroundService"', 1)[1].split("</service>", 1)[0]
    assert 'android:exported="false"' in service_block
    assert "android.permission.BIND_ACCESSIBILITY_SERVICE" in m
    assert "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" in m


def test_low_resource_model_policy_is_preserved():
    low = text("scripts/install-android-low-resource-profile.sh")
    assert '"persistent_model": False' in low
    assert '"agent_planning_with_local_model": False' in low


def test_pairing_token_is_local_and_private():
    p = text("scripts/pair-android-companion.sh")
    assert "secrets.token_urlsafe" in p
    assert "chmod 600" in p
    assert "hakim://pair?token=" in p


def test_companion_self_heals_without_remote_bridge_dependency():
    service = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimForegroundService.kt")
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    manifest = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert "START_STICKY" in service
    assert "companion_heartbeat_ms" in service
    assert 'putBoolean("persistent_model_allowed", false)' in service
    assert "server?.isListening()" in service
    assert "fun isListening()" in server
    assert "android.intent.action.MY_PACKAGE_REPLACED" in manifest


def test_status_separates_runtime_health_from_field_evidence():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert '.put("evidence_state", "NOT_PROVEN")' in server
    assert '.put("runtime_health", prefs.getString("companion_mode", "UNKNOWN"))' in server
    assert '.put("persistent_model", JSONObject.NULL)' in server
    assert '.put("persistent_model_evidence", "NOT_PROVEN")' in server
    assert '.put("persistent_model_allowed", false)' in server
    assert '.put("status", "PASS")' not in server
    assert '.put("persistent_model", false)' not in server
