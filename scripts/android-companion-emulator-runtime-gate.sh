#!/system/bin/sh
# POSIX-compatible Android emulator runtime qualification gate.
# This is pre-field evidence only; it never qualifies a physical TECNO/HiOS device.
# Runtime-only grants/settings are permitted only inside this disposable CI emulator.
# Physical-device Human Gates and LOCAL_DEVICE_ONLY signing remain untouched.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"
ACCESSIBILITY_SERVICE="${PKG}/.HakimAccessibilityService"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }
require_json() { printf '%s' "$1" | grep -F "$2" >/dev/null || { echo "$3: missing $2" >&2; printf '%s\n' "$1" >&2; exit 1; }; }

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS
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
require_json "$status" '"control_server_listening":true' 'status semantics'
require_json "$status" '"persistent_model":null' 'status semantics'
require_json "$status" '"persistent_model_evidence":"NOT_PROVEN"' 'status semantics'
require_json "$status" '"persistent_model_allowed":false' 'status semantics'
require_json "$status" '"accessibility":false' 'status precondition'
echo 'STAGE_STATUS_SEMANTICS=PROVEN'

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No kernel listener found for Companion port' >&2; adb shell ss -ltn >&2 || true; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener is not visibly loopback-bound' >&2; printf '%s\n' "$listen" >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion control plane is wildcard-bound' >&2; exit 1; fi
echo 'STAGE_KERNEL_LOOPBACK=PROVEN'

code=$(curl -sS -o /tmp/hakim-ui-unavailable.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
[ "$code" = '409' ] || fail_http 'UI without Accessibility' 409 "$code" /tmp/hakim-ui-unavailable.json
grep -F '"error":"accessibility_unavailable"' /tmp/hakim-ui-unavailable.json >/dev/null || { cat /tmp/hakim-ui-unavailable.json >&2; exit 1; }
echo 'STAGE_UI_FAIL_CLOSED=PROVEN'
code=$(curl -sS -o /tmp/hakim-screenshot-unavailable.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/screenshot")
[ "$code" = '409' ] || fail_http 'screenshot without Accessibility' 409 "$code" /tmp/hakim-screenshot-unavailable.json
grep -F '"error":"screenshot_unavailable"' /tmp/hakim-screenshot-unavailable.json >/dev/null || { cat /tmp/hakim-screenshot-unavailable.json >&2; exit 1; }
echo 'STAGE_SCREENSHOT_FAIL_CLOSED=PROVEN'
code=$(curl -sS -o /tmp/hakim-action-unavailable.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d '{"action":"back"}' "${BASE_URL}/v1/action")
[ "$code" = '409' ] || fail_http 'action without Accessibility' 409 "$code" /tmp/hakim-action-unavailable.json
grep -F '"ok":false' /tmp/hakim-action-unavailable.json >/dev/null || { cat /tmp/hakim-action-unavailable.json >&2; exit 1; }
echo 'STAGE_ACTION_FAIL_CLOSED=PROVEN'

adb shell settings put secure enabled_accessibility_services "$ACCESSIBILITY_SERVICE"
adb shell settings put secure accessibility_enabled 1

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-accessibility.json 2>/dev/null && grep -F '"accessibility":true' /tmp/hakim-status-accessibility.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Accessibility service did not become ready in emulator' >&2; cat /tmp/hakim-status-accessibility.json >&2 || true; exit 1; }; sleep 1
done
echo 'STAGE_ACCESSIBILITY_CONNECTED=PROVEN'

adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
i=0
while [ "$i" -lt 20 ]; do
  code=$(curl -sS -o /tmp/hakim-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  if [ "$code" = '200' ] && python3 - <<'PY'
import json
with open('/tmp/hakim-ui.json', encoding='utf-8') as f: obj=json.load(f)
nodes=obj.get('nodes')
raise SystemExit(0 if isinstance(nodes,list) and nodes and any(n.get('class') for n in nodes) else 1)
PY
  then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 20 ] || { echo 'Accessibility UI tree did not become non-empty' >&2; cat /tmp/hakim-ui.json >&2 || true; exit 1; }
echo 'STAGE_UI_TREE=PROVEN'

# Capture response even if the endpoint reports an error; diagnostics must survive curl failure.
code=$(curl -sS -o /tmp/hakim-screenshot.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/screenshot") || { rc=$?; echo "Screenshot request transport failed rc=$rc" >&2; cat /tmp/hakim-screenshot.json >&2 || true; exit "$rc"; }
echo "STAGE_SCREENSHOT_HTTP=$code"
[ "$code" = '200' ] || fail_http 'screenshot with Accessibility' 200 "$code" /tmp/hakim-screenshot.json
python3 - <<'PY'
import base64,json
with open('/tmp/hakim-screenshot.json',encoding='utf-8') as f: obj=json.load(f)
data=base64.b64decode(obj['png_base64'],validate=True)
assert len(data)>1000,len(data)
assert data.startswith(b'\x89PNG\r\n\x1a\n'),data[:8]
PY
echo 'STAGE_SCREENSHOT=PROVEN'

code=$(curl -sS -o /tmp/hakim-action-home.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d '{"action":"home"}' "${BASE_URL}/v1/action")
[ "$code" = '200' ] || fail_http 'HOME action' 200 "$code" /tmp/hakim-action-home.json
grep -F '"ok":true' /tmp/hakim-action-home.json >/dev/null
sleep 1
if adb shell dumpsys activity activities | grep -F "mResumedActivity" | grep -F "$PKG" >/dev/null; then echo 'HOME action did not produce an observable navigation result' >&2; exit 1; fi
echo 'STAGE_NAVIGATION=PROVEN'

code=$(curl -sS -o /tmp/hakim-launch.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '200' ] || fail_http 'bounded launch' 200 "$code" /tmp/hakim-launch.json
grep -F '"ok":true' /tmp/hakim-launch.json >/dev/null
sleep 1
adb shell dumpsys activity activities | grep -F "mResumedActivity" | grep -F "$PKG" >/dev/null

adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity"
adb shell pidof "$PKG" >/dev/null
curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-restart.json
printf '%s' "$(cat /tmp/hakim-status-after-restart.json)" | grep -F '"persistent_model_allowed":false' >/dev/null
if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then echo 'Unexpected resident local-model process' >&2; exit 1; fi

adb reboot
adb wait-for-device
boot=''; i=0
while [ "$i" -lt 90 ]; do boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r'); [ "$boot" = '1' ] && break; i=$((i + 1)); sleep 2; done
[ "$boot" = '1' ]
adb shell pm path "$PKG" | grep '^package:'
adb shell am start -W -n "$PKG/.MainActivity"
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}"
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-reboot.json 2>/dev/null; do i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Authenticated control plane did not recover after reboot' >&2; exit 1; }; sleep 1; done
printf '%s' "$(cat /tmp/hakim-status-after-reboot.json)" | grep -F '"evidence_state":"NOT_PROVEN"' >/dev/null
printf '%s' "$(cat /tmp/hakim-status-after-reboot.json)" | grep -F '"persistent_model_allowed":false' >/dev/null

echo 'EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_ACCESSIBILITY_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_PAIRING=SCAFFOLD_ONLY'
echo 'EMULATOR_AUTH_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_LOOPBACK_BINDING=PROVEN'
echo 'EMULATOR_STATUS_SEMANTICS=PROVEN'
echo 'EMULATOR_PERMISSION_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_UI_TREE=PROVEN'
echo 'EMULATOR_SCREENSHOT=PROVEN'
echo 'EMULATOR_NAVIGATION=PROVEN'
echo 'EMULATOR_PAIRING_RECOVERY=PROVEN'
echo 'EMULATOR_CONTROL_PLANE=PROVEN'
echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN'
