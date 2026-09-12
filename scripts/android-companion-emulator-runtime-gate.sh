#!/system/bin/sh
# POSIX-compatible Android 15 emulator runtime qualification gate for HAKIM sovereign-local mode.
# Pre-field evidence only; it never qualifies a physical device.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
ACTION_RID="emulator-local-proof-0001"
LAUNCH_REQUEST_ID="emulator-launch-0001"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }
require_json() { printf '%s' "$1" | grep -F "$2" >/dev/null || { echo "$3: missing $2" >&2; printf '%s\n' "$1" >&2; exit 1; }; }

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS || true
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb shell am start -W -a android.intent.action.VIEW -d "hakim://pair?token=${PAIR_TOKEN}" "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane did not become ready' >&2; exit 1; }; sleep 1
done
echo 'STAGE_CONTROL_READY=PROVEN'

code=$(curl -sS -o /tmp/hakim-missing-auth.json -w '%{http_code}' "${BASE_URL}/v1/status")
[ "$code" = '401' ] || fail_http 'missing auth fail-closed' 401 "$code" /tmp/hakim-missing-auth.json
code=$(curl -sS -o /tmp/hakim-wrong-auth.json -w '%{http_code}' -H 'Authorization: Bearer definitely-wrong-token' "${BASE_URL}/v1/status")
[ "$code" = '401' ] || fail_http 'wrong auth fail-closed' 401 "$code" /tmp/hakim-wrong-auth.json
echo 'STAGE_AUTH_FAIL_CLOSED=PROVEN'

status=$(cat /tmp/hakim-status.json)
require_json "$status" '"evidence_state":"NOT_PROVEN"' 'status semantics'
require_json "$status" '"loopback_only":true' 'status semantics'
require_json "$status" '"control_server_listening":true' 'status semantics'
require_json "$status" '"persistent_model":null' 'status semantics'
require_json "$status" '"persistent_model_allowed":false' 'status semantics'
require_json "$status" '"external_transport_enabled":false' 'sovereign local semantics'
require_json "$status" '"accessibility":false' 'sovereign local semantics'
require_json "$status" '"notification_listener":false' 'sovereign local semantics'
require_json "$status" '"attached":true' 'browser readiness'
require_json "$status" '"mode":"SOVEREIGN_LOCAL_BROWSER"' 'browser mode'
echo 'STAGE_SOVEREIGN_STATUS=PROVEN'

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No kernel listener found for Companion port' >&2; adb shell ss -ltn >&2 || true; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener is not visibly loopback-bound' >&2; printf '%s\n' "$listen" >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion control plane is wildcard-bound' >&2; exit 1; fi
echo 'STAGE_KERNEL_LOOPBACK=PROVEN'

# Notification reading must stay unavailable in the Play-Protect-safe sovereign release.
code=$(curl -sS -o /tmp/hakim-notifications-disabled.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications intentionally disabled' 409 "$code" /tmp/hakim-notifications-disabled.json
grep -F 'notification_listener_disabled_by_play_protect_safe_mode' /tmp/hakim-notifications-disabled.json >/dev/null || { cat /tmp/hakim-notifications-disabled.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_SURFACE_ABSENT=PROVEN'

# A mutating browser action must require a durable request identity.
PROOF='{"action":"local_proof","message":"اختبار حكيم السيادي المحلي داخل المحاكي"}'
code=$(curl -sS -o /tmp/hakim-proof-no-id.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "$PROOF" "${BASE_URL}/v1/action")
[ "$code" = '400' ] || fail_http 'local proof missing request identity' 400 "$code" /tmp/hakim-proof-no-id.json
grep -F 'request_id_required' /tmp/hakim-proof-no-id.json >/dev/null

code=$(curl -sS -o /tmp/hakim-proof.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${ACTION_RID}" -H 'Content-Type: application/json' -d "$PROOF" "${BASE_URL}/v1/action")
[ "$code" = '200' ] || fail_http 'offline local proof action' 200 "$code" /tmp/hakim-proof.json
grep -F '"ok":true' /tmp/hakim-proof.json >/dev/null
echo 'STAGE_LOCAL_PROOF_ACTION=PROVEN'

# Observe the owned WebView after the local, no-network proof page is rendered.
i=0
while [ "$i" -lt 20 ]; do
  code=$(curl -sS -o /tmp/hakim-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  if [ "$code" = '200' ] && grep -F '"mode":"browser_dom"' /tmp/hakim-ui.json >/dev/null && grep -F 'hakim.local' /tmp/hakim-ui.json >/dev/null; then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 20 ] || { echo 'Owned browser did not expose the local proof page' >&2; cat /tmp/hakim-ui.json >&2 || true; exit 1; }
echo 'STAGE_BROWSER_DOM=PROVEN'

code=$(curl -sS -o /tmp/hakim-screenshot.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/screenshot")
[ "$code" = '200' ] || fail_http 'owned browser screenshot' 200 "$code" /tmp/hakim-screenshot.json
python3 - <<'PY'
import base64,json
with open('/tmp/hakim-screenshot.json',encoding='utf-8') as f: obj=json.load(f)
data=base64.b64decode(obj['png_base64'],validate=True)
assert len(data)>1000,len(data)
assert data.startswith(b'\x89PNG\r\n\x1a\n'),data[:8]
assert obj.get('mode') == 'browser_view'
PY
echo 'STAGE_BROWSER_SCREENSHOT=PROVEN'

# Replay must be rejected before a second side effect.
code=$(curl -sS -o /tmp/hakim-proof-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${ACTION_RID}" -H 'Content-Type: application/json' -d "$PROOF" "${BASE_URL}/v1/action")
[ "$code" = '409' ] || fail_http 'local proof replay' 409 "$code" /tmp/hakim-proof-replay.json
grep -F 'duplicate_request' /tmp/hakim-proof-replay.json >/dev/null
echo 'STAGE_ACTION_REPLAY_PROTECTION=PROVEN'

# Bounded app launch is still allowlisted and replay protected.
code=$(curl -sS -o /tmp/hakim-launch-missing-id.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '400' ] || fail_http 'bounded launch missing request identity' 400 "$code" /tmp/hakim-launch-missing-id.json
code=$(curl -sS -o /tmp/hakim-launch.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '200' ] || fail_http 'bounded launch' 200 "$code" /tmp/hakim-launch.json
grep -F '"ok":true' /tmp/hakim-launch.json >/dev/null
echo 'STAGE_BOUNDED_LAUNCH=PROVEN'

adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-restart.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane did not recover after process death' >&2; exit 1; }; sleep 1
done
grep -F '"external_transport_enabled":false' /tmp/hakim-status-after-restart.json >/dev/null
code=$(curl -sS -o /tmp/hakim-launch-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '409' ] || fail_http 'bounded launch replay after process death' 409 "$code" /tmp/hakim-launch-replay.json
grep -F 'duplicate_request' /tmp/hakim-launch-replay.json >/dev/null
echo 'STAGE_PROCESS_RECOVERY_AND_DURABLE_REPLAY=PROVEN'

if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then echo 'Unexpected resident local-model process' >&2; exit 1; fi

adb reboot
adb wait-for-device
boot=''; i=0
while [ "$i" -lt 90 ]; do boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r'); [ "$boot" = '1' ] && break; i=$((i + 1)); sleep 2; done
[ "$boot" = '1' ]
adb shell pm path "$PKG" | grep '^package:'
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-reboot.json 2>/dev/null; do i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Authenticated control plane did not recover after reboot' >&2; exit 1; }; sleep 1; done
grep -F '"loopback_only":true' /tmp/hakim-status-after-reboot.json >/dev/null
grep -F '"external_transport_enabled":false' /tmp/hakim-status-after-reboot.json >/dev/null

echo 'EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_PAIRING=SCAFFOLD_ONLY'
echo 'EMULATOR_AUTH_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_LOOPBACK_BINDING=PROVEN'
echo 'EMULATOR_STATUS_SEMANTICS=PROVEN'
echo 'EMULATOR_EXTERNAL_TRANSPORT_ABSENT=PROVEN'
echo 'EMULATOR_LOCAL_PROOF=PROVEN'
echo 'EMULATOR_BROWSER_DOM=PROVEN'
echo 'EMULATOR_BROWSER_SCREENSHOT=PROVEN'
echo 'EMULATOR_ACTION_REPLAY_PROTECTION=PROVEN'
echo 'EMULATOR_LAUNCH_REPLAY_PROTECTION=PROVEN'
echo 'EMULATOR_PAIRING_RECOVERY=PROVEN'
echo 'EMULATOR_CONTROL_PLANE=PROVEN'
echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_PHONE_FIELD_QUALIFICATION=NOT_PROVEN'
