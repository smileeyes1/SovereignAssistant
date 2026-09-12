from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion"
JAVA = APP / "app/src/main/java/org/hakim/omega/companion"


def text(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_companion_is_loopback_and_token_gated():
    s = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert "InetAddress.getLoopbackAddress()" in s
    assert 'headers["authorization"]' in s
    assert "Bearer $token" in s
    assert "0.0.0.0" not in s


def test_control_service_is_private_and_sensitive_android_services_are_absent():
    m = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'android:name=".HakimForegroundService"' in m
    service_block = m.split('android:name=".HakimForegroundService"', 1)[1].split("</service>", 1)[0]
    assert 'android:exported="false"' in service_block
    assert "BIND_ACCESSIBILITY_SERVICE" not in m
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" not in m
    assert not (JAVA / "HakimAccessibilityService.kt").exists()
    assert not (JAVA / "HakimNotificationListener.kt").exists()
    assert not (JAVA / "HakimRemoteRelay.kt").exists()


def test_low_resource_model_policy_is_preserved():
    low = text("scripts/install-android-low-resource-profile.sh")
    assert '"persistent_model": False' in low
    assert '"agent_planning_with_local_model": False' in low


def test_pairing_token_is_local_private_and_provider_independent():
    p = text("scripts/pair-android-companion.sh")
    assert "secrets.token_urlsafe" in p
    assert "chmod 600" in p
    assert "hakim://pair?token=" in p
    assert "relay" not in p.lower()
    assert "make" not in p.lower()


def test_companion_self_heals_local_server_without_remote_bridge_dependency():
    service = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimForegroundService.kt")
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    manifest = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert "START_STICKY" in service
    assert "companion_heartbeat_ms" in service
    assert 'putBoolean("persistent_model_allowed", false)' in service
    assert 'putBoolean("external_transport_enabled", false)' in service
    assert "server?.isListening()" in service
    assert "HakimRemoteRelay" not in service
    assert "fun isListening()" in server
    assert "android.intent.action.MY_PACKAGE_REPLACED" in manifest


def test_status_separates_runtime_health_from_field_evidence_and_discloses_zero_transport():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert '.put("evidence_state", "NOT_PROVEN")' in server
    assert '.put("runtime_health", prefs.getString("companion_mode", "UNKNOWN"))' in server
    assert '.put("persistent_model", JSONObject.NULL)' in server
    assert '.put("persistent_model_evidence", "NOT_PROVEN")' in server
    assert '.put("persistent_model_allowed", false)' in server
    assert '.put("external_transport_enabled", false)' in server
    assert '.put("accessibility", false)' in server
    assert '.put("notification_listener", false)' in server
    assert '.put("status", "PASS")' not in server


def test_ui_endpoint_uses_owned_browser_and_fails_closed_before_browser_is_available():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    browser = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimBrowserController.kt")
    assert 'path == "/v1/ui"' in server
    assert 'JSONObject().put("error", "browser_unavailable")' in server
    assert '.put("nodes", HakimBrowserController.uiSnapshot())' in server
    assert '"mode", "browser_dom"' in server
    assert "document.querySelectorAll" in browser
    assert '.put("mode", "SOVEREIGN_LOCAL_BROWSER")' in browser


def test_notification_endpoint_is_intentionally_disabled_and_cannot_leak_notifications():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert '.put("notification_listener", false)' in server
    assert 'notification_listener_disabled_by_play_protect_safe_mode' in server
    assert 'path == "/v1/notifications"' in server


def test_owned_browser_supports_local_proof_and_browser_only_screenshot():
    browser = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimBrowserController.kt")
    assert '"local_proof" -> showLocalProof' in browser
    assert 'loadDataWithBaseURL("https://hakim.local/"' in browser
    assert "Bitmap.createBitmap" in browser
    assert "w.draw(canvas)" in browser
    assert "evaluateJavascript" in browser


def test_emulator_gate_runs_as_one_posix_process_and_cannot_claim_physical_field_pass():
    workflow = text(".github/workflows/android-companion.yml")
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert "script: sh scripts/android-companion-emulator-runtime-gate.sh" in workflow
    assert "set -eu" in gate
    assert "pipefail" not in gate
    assert "EMULATOR_RUNTIME=PROVEN" in gate
    assert "PHYSICAL_PHONE_FIELD_QUALIFICATION=NOT_PROVEN" in gate
    assert "EMULATOR_EXTERNAL_TRANSPORT_ABSENT=PROVEN" in gate
    assert "EMULATOR_LOCAL_PROOF=PROVEN" in gate
    assert "BIND_ACCESSIBILITY_SERVICE" not in gate
    assert "enabled_accessibility_services" not in gate


def test_emulator_gate_exercises_authenticated_local_control_and_fail_closed_semantics():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert 'adb forward "tcp:${PORT}" "tcp:${PORT}"' in gate
    assert "hakim://pair?token=${PAIR_TOKEN}" in gate
    assert "Authorization: Bearer ${PAIR_TOKEN}" in gate
    assert "definitely-wrong-token" in gate
    assert "[ \"$code\" = '401' ]" in gate
    assert '"evidence_state":"NOT_PROVEN"' in gate
    assert '"loopback_only":true' in gate
    assert '"control_server_listening":true' in gate
    assert '"external_transport_enabled":false' in gate
    assert 'notification_listener_disabled_by_play_protect_safe_mode' in gate
    assert "STAGE_AUTH_FAIL_CLOSED=PROVEN" in gate
    assert "STAGE_SOVEREIGN_STATUS=PROVEN" in gate


def test_emulator_gate_proves_local_browser_dom_screenshot_and_replay_protection():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert '"action":"local_proof"' in gate
    assert '"${BASE_URL}/v1/ui"' in gate
    assert '"mode":"browser_dom"' in gate
    assert "hakim.local" in gate
    assert '"${BASE_URL}/v1/screenshot"' in gate
    assert "base64.b64decode" in gate
    assert "data.startswith(b'\\x89PNG\\r\\n\\x1a\\n')" in gate
    assert "STAGE_BROWSER_DOM=PROVEN" in gate
    assert "STAGE_BROWSER_SCREENSHOT=PROVEN" in gate
    assert "STAGE_ACTION_REPLAY_PROTECTION=PROVEN" in gate


def test_emulator_gate_proves_kernel_loopback_binding_and_pairing_recovery():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert "adb shell ss -ltn" in gate
    assert "Companion control plane is wildcard-bound" in gate
    assert "STAGE_KERNEL_LOOPBACK=PROVEN" in gate
    assert "hakim-status-after-restart.json" in gate
    assert "hakim-status-after-reboot.json" in gate
    assert "Authenticated control plane did not recover after reboot" in gate
    assert "EMULATOR_PAIRING_RECOVERY=PROVEN" in gate


def test_launch_requires_durable_identity_and_runtime_gate_proves_replay_rejection():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    launch_block = server.split('path == "/v1/launch"', 1)[1].split('else -> respond(c, 404', 1)[0]
    assert 'headers["x-hakim-request-id"]' in launch_block
    assert 'JSONObject().put("error", "request_id_required")' in launch_block
    assert '!claimRequest(requestId)' in launch_block
    assert 'JSONObject().put("error", "duplicate_request")' in launch_block
    assert 'context.startActivity(intent)' in launch_block
    assert 'LAUNCH_REQUEST_ID="emulator-launch-0001"' in gate
    assert 'X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}' in gate
    assert "bounded launch replay after process death" in gate
    assert "STAGE_PROCESS_RECOVERY_AND_DURABLE_REPLAY=PROVEN" in gate
