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


def test_control_service_is_not_exported_and_safe_core_omits_sensitive_bindings():
    m = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'android:name=".HakimForegroundService"' in m
    service_block = m.split('android:name=".HakimForegroundService"', 1)[1].split("</service>", 1)[0]
    assert 'android:exported="false"' in service_block
    assert "android.permission.BIND_ACCESSIBILITY_SERVICE" not in m
    assert "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" not in m
    assert ".HakimAccessibilityService" not in m
    assert ".HakimNotificationListener" not in m


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
    assert '.put("safe_core", true)' in server
    assert '.put("control_scope", "OWNED_BROWSER_ONLY")' in server
    assert '.put("device_wide_accessibility", false)' in server
    assert '.put("notification_access", false)' in server
    assert '.put("status", "PASS")' not in server
    assert '.put("persistent_model", false)' not in server


def test_ui_endpoint_is_owned_browser_only_and_fails_closed_if_browser_missing():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert 'path == "/v1/ui"' in server
    assert 'browser_unavailable' in server
    assert 'respond(c, 409' in server
    assert 'HakimBrowserController.uiSnapshot()' in server
    assert 'HakimAccessibilityService' not in server


def test_notification_endpoint_is_explicitly_disabled_in_safe_core():
    server = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt")
    assert 'path == "/v1/notifications"' in server
    assert '"disabled_in_safe_core"' in server
    assert '"notification_access_not_registered"' in server
    assert 'HakimNotificationListener' not in server


def test_legacy_accessibility_implementation_keeps_package_identity_if_used_in_optional_profile():
    service = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimAccessibilityService.kt")
    assert '.put("package", n.packageName?.toString().orEmpty())' in service


def test_emulator_gate_runs_as_one_posix_process_and_cannot_claim_physical_field_pass():
    workflow = text(".github/workflows/android-companion.yml")
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert "script: sh scripts/android-companion-emulator-runtime-gate.sh" in workflow
    assert "set -eu" in gate
    assert "pipefail" not in gate
    assert 'pm grant "$PKG" android.permission.POST_NOTIFICATIONS' in gate
    assert "EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY" in gate
    assert "EMULATOR_ACCESSIBILITY_PERMISSION=SCAFFOLD_ONLY" in gate
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
    assert "EMULATOR_AUTH_FAIL_CLOSED=PROVEN" in gate
    assert "EMULATOR_STATUS_SEMANTICS=PROVEN" in gate
    assert "EMULATOR_CONTROL_PLANE=PROVEN" in gate


def test_emulator_gate_retains_legacy_device_wide_profile_checks_separate_from_safe_core():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert 'settings put secure enabled_accessibility_services "$ACCESSIBILITY_SERVICE"' in gate
    assert "settings put secure accessibility_enabled 1" in gate
    assert '"${BASE_URL}/v1/ui"' in gate
    assert '"${BASE_URL}/v1/screenshot"' in gate
    assert "EMULATOR_UI_TREE=PROVEN" in gate
    assert "EMULATOR_SCREENSHOT=PROVEN" in gate
    assert "EMULATOR_NAVIGATION=PROVEN" in gate


def test_emulator_gate_proves_kernel_loopback_binding_and_pairing_recovery():
    gate = text("scripts/android-companion-emulator-runtime-gate.sh")
    assert "adb shell ss -ltn" in gate
    assert "Companion control plane is wildcard-bound" in gate
    assert "EMULATOR_LOOPBACK_BINDING=PROVEN" in gate
    assert "hakim-status-after-restart.json" in gate
    assert "hakim-status-after-reboot.json" in gate
    assert "Authenticated control plane did not recover after reboot" in gate
    assert "EMULATOR_PAIRING_RECOVERY=PROVEN" in gate
    assert "EMULATOR_PERMISSION_FAIL_CLOSED=PROVEN" in gate


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
    assert "bounded launch missing request identity" in gate
    assert "bounded launch replay after process death" in gate
    assert '"error":"duplicate_request"' in gate
    assert "STAGE_LAUNCH_REPLAY_PROTECTION=PROVEN" in gate
    assert "EMULATOR_LAUNCH_REPLAY_PROTECTION=PROVEN" in gate
