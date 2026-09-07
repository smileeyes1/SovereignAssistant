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


def test_emulator_gate_runs_as_one_posix_process_and_cannot_claim_physical_field_pass():
    workflow = text(".github/workflows/android-companion.yml")
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert "script: sh scripts/android-companion-emulator-runtime-gate.sh" in workflow
    assert "set -eu" in gate
    assert "pipefail" not in gate
    assert 'pm grant "$PKG" android.permission.POST_NOTIFICATIONS' in gate
    assert "EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY" in gate
    assert "EMULATOR_PAIRING=SCAFFOLD_ONLY" in gate
    assert "EMULATOR_RUNTIME=PROVEN" in gate
    assert "PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN" in gate
    assert "llama-server" in gate
    assert "adb reboot" in gate


def test_emulator_gate_exercises_authenticated_control_plane_and_fail_closed_semantics():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert 'adb forward "tcp:${PORT}" "tcp:${PORT}"' in gate
    assert "hakim://pair?token=${PAIR_TOKEN}" in gate
    assert "Authorization: Bearer ${PAIR_TOKEN}" in gate
    assert "definitely-wrong-token" in gate
    assert "[ \"$code\" = '401' ]" in gate
    assert '"evidence_state":"NOT_PROVEN"' in gate
    assert '"loopback_only":true' in gate
    assert '"control_server_listening":true' in gate
    assert '"persistent_model":null' in gate
    assert '"persistent_model_allowed":false' in gate
    assert "screenshot_unavailable" in gate
    assert '"ok":false' in gate
    assert '"ok":true' in gate
    assert "EMULATOR_AUTH_FAIL_CLOSED=PROVEN" in gate
    assert "EMULATOR_STATUS_SEMANTICS=PROVEN" in gate
    assert "EMULATOR_CONTROL_PLANE=PROVEN" in gate
