#!/system/bin/sh
# POSIX-compatible Android 15 emulator qualification for the safe browser core.
# Pre-field evidence only; never qualifies the physical TECNO/HiOS device.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
OPEN_ID="emulator-browser-open-0001"
RELOAD_ID="emulator-browser-reload-0001"
LAUNCH_REQUEST_ID="emulator-launch-0001"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }
require_json() { printf '%s' "$1" | grep -F "$2" >/dev/null || { echo "$3: missing $2" >&2; printf '%s\n' "$1" >&2; exit 1; }; }

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS || true
adb shell am start -W -n "$PKG/.MainActivity"
adb shell dumpsys activity activities | grep -F "$PKG" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb shell am start -W -a android.intent.action.VIEW -d "hakim://pair?token=${PAIR_TOKEN}" "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}"

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
require_json "$status" '"safe_core":true' 'safe core semantics'
require_json "$status" '"control_scope":"OWNED_BROWSER_ONLY"' 'safe core scope'
require_json "$status" '"device_wide_accessibility":false' 'safe core scope'
require_json "$status" '"notification_access":false' 'safe core scope'
require_json "$status" '"control_server_listening":true' 'status semantics'
require_json "$status" '"persistent_model":null' 'status semantics'
require_json "$status" '"persistent_model_evidence":"NOT_PROVEN"' 'status semantics'
require_json "$status" '"persistent_model_allowed":false' 'status semantics'
echo 'STAGE_STATUS_SEMANTICS=PROVEN'

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No kernel listener found for Companion port' >&2; adb shell ss -ltn >&2 || true; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener is not visibly loopback-bound' >&2; printf '%s\n' "$listen" >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion control plane is wildcard-bound' >&2; exit 1; fi
echo 'STAGE_KERNEL_LOOPBACK=PROVEN'

# The safe core must not expose device-wide sensitive services in package metadata.
if adb shell dumpsys package "$PKG" | grep -E 'HakimAccessibilityService|HakimNotificationListener' >/dev/null; then
  echo 'Sensitive device-wide service unexpectedly registered in safe core' >&2
  exit 1
fi
echo 'STAGE_SENSITIVE_SERVICES_ABSENT=PROVEN'

# Owned browser is attached even before navigation. Compatibility UI endpoint must
# resolve to the owned browser rather than device-wide Accessibility.
code=$(curl -sS -o /tmp/hakim-ui-initial.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
[ "$code" = '200' ] || fail_http 'owned browser UI endpoint' 200 "$code" /tmp/hakim-ui-initial.json
grep -F '"scope":"OWNED_BROWSER_ONLY"' /tmp/hakim-ui-initial.json >/dev/null || { cat /tmp/hakim-ui-initial.json >&2; exit 1; }
echo 'STAGE_OWNED_BROWSER_UI_ENDPOINT=PROVEN'

# Open a stable HTTPS page through the exact compatibility action route.
code=$(curl -sS -o /tmp/hakim-browser-open.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${OPEN_ID}" -H 'Content-Type: application/json' -d '{"action":"browser_open","url":"https://example.com"}' "${BASE_URL}/v1/action")
[ "$code" = '200' ] || fail_http 'owned browser open' 200 "$code" /tmp/hakim-browser-open.json
grep -F '"ok":true' /tmp/hakim-browser-open.json >/dev/null || { cat /tmp/hakim-browser-open.json >&2; exit 1; }

i=0
while [ "$i" -lt 30 ]; do
  code=$(curl -sS -o /tmp/hakim-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  if [ "$code" = '200' ] && grep -F 'example.com' /tmp/hakim-ui.json >/dev/null; then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 30 ] || { echo 'Owned browser did not navigate to HTTPS fixture' >&2; cat /tmp/hakim-ui.json >&2 || true; exit 1; }
echo 'STAGE_OWNED_BROWSER_NAVIGATION=PROVEN'

code=$(curl -sS -o /tmp/hakim-screenshot.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/screenshot")
[ "$code" = '200' ] || fail_http 'owned browser screenshot' 200 "$code" /tmp/hakim-screenshot.json
python3 - <<'PY'
import base64,json
with open('/tmp/hakim-screenshot.json',encoding='utf-8') as f: obj=json.load(f)
data=base64.b64decode(obj['png_base64'],validate=True)
assert len(data)>1000,len(data)
assert data.startswith(b'\x89PNG\r\n\x1a\n'),data[:8]
assert obj.get('mode')=='owned_browser_view',obj
PY
echo 'STAGE_OWNED_BROWSER_SCREENSHOT=PROVEN'

# Browser mutation requires identity, executes once, then rejects exact replay.
code=$(curl -sS -o /tmp/hakim-reload-no-id.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d '{"action":"browser_reload"}' "${BASE_URL}/v1/action")
[ "$code" = '400' ] || fail_http 'browser reload missing request identity' 400 "$code" /tmp/hakim-reload-no-id.json
grep -F '"error":"request_id_required"' /tmp/hakim-reload-no-id.json >/dev/null
code=$(curl -sS -o /tmp/hakim-reload.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RELOAD_ID}" -H 'Content-Type: application/json' -d '{"action":"browser_reload"}' "${BASE_URL}/v1/action")
[ "$code" = '200' ] || fail_http 'identified browser reload' 200 "$code" /tmp/hakim-reload.json
code=$(curl -sS -o /tmp/hakim-reload-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RELOAD_ID}" -H 'Content-Type: application/json' -d '{"action":"browser_reload"}' "${BASE_URL}/v1/action")
[ "$code" = '409' ] || fail_http 'browser reload replay' 409 "$code" /tmp/hakim-reload-replay.json
grep -F '"error":"duplicate_request"' /tmp/hakim-reload-replay.json >/dev/null
echo 'STAGE_OWNED_BROWSER_ACTION_IDEMPOTENCY=PROVEN'

# Notification data is intentionally unavailable in the safe core.
code=$(curl -sS -o /tmp/hakim-notifications-disabled.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '410' ] || fail_http 'safe-core notifications disabled' 410 "$code" /tmp/hakim-notifications-disabled.json
grep -F '"error":"disabled_in_safe_core"' /tmp/hakim-notifications-disabled.json >/dev/null
echo 'STAGE_NOTIFICATION_ACCESS_ABSENT=PROVEN'

# Bounded launch remains request-ID protected.
code=$(curl -sS -o /tmp/hakim-launch-missing-id.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '400' ] || fail_http 'bounded launch missing request identity' 400 "$code" /tmp/hakim-launch-missing-id.json
code=$(curl -sS -o /tmp/hakim-launch.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '200' ] || fail_http 'bounded launch' 200 "$code" /tmp/hakim-launch.json
grep -F '"ok":true' /tmp/hakim-launch.json >/dev/null
echo 'STAGE_BOUNDED_LAUNCH=PROVEN'

# Pairing and replay ledger survive process death.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-restart.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane did not recover after process death' >&2; exit 1; }; sleep 1
done
code=$(curl -sS -o /tmp/hakim-launch-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '409' ] || fail_http 'bounded launch replay after process death' 409 "$code" /tmp/hakim-launch-replay.json
grep -F '"error":"duplicate_request"' /tmp/hakim-launch-replay.json >/dev/null
echo 'STAGE_PROCESS_RECOVERY_AND_REPLAY_LEDGER=PROVEN'
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
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-reboot.json 2>/dev/null; do i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Authenticated safe core did not recover after reboot' >&2; exit 1; }; sleep 1; done
reboot_status=$(cat /tmp/hakim-status-after-reboot.json)
require_json "$reboot_status" '"safe_core":true' 'post-reboot safe core'
require_json "$reboot_status" '"control_scope":"OWNED_BROWSER_ONLY"' 'post-reboot safe core'
require_json "$reboot_status" '"persistent_model_allowed":false' 'post-reboot model policy'

echo 'EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_ACCESSIBILITY_PERMISSION=NOT_REGISTERED_SAFE_CORE'
echo 'EMULATOR_PAIRING=SCAFFOLD_ONLY'
echo 'EMULATOR_AUTH_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_LOOPBACK_BINDING=PROVEN'
echo 'EMULATOR_STATUS_SEMANTICS=PROVEN'
echo 'EMULATOR_PERMISSION_FAIL_CLOSED=PROVEN_SAFE_CORE'
echo 'EMULATOR_UI_TREE=PROVEN_OWNED_BROWSER_ONLY'
echo 'EMULATOR_SCREENSHOT=PROVEN_OWNED_BROWSER_ONLY'
echo 'EMULATOR_NAVIGATION=PROVEN_OWNED_BROWSER_ONLY'
echo 'EMULATOR_ACTION_IDEMPOTENCY=PROVEN_OWNED_BROWSER_ONLY'
echo 'EMULATOR_LAUNCH_REPLAY_PROTECTION=PROVEN'
echo 'EMULATOR_PAIRING_RECOVERY=PROVEN'
echo 'EMULATOR_CONTROL_PLANE=PROVEN'
echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN'
