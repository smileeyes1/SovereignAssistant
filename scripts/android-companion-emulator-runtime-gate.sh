#!/system/bin/sh
# بوابة تأهيل محاكي حكيم السيادي المحلي. هذا دليل قبل ميداني فقط ولا يثبت الهاتف الحقيقي.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
ACTION_REQUEST_ID="emulator-action-0001"
LAUNCH_REQUEST_ID="emulator-launch-0001"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }
require_json() { printf '%s' "$1" | grep -F "$2" >/dev/null || { echo "$3: missing $2" >&2; printf '%s\n' "$1" >&2; exit 1; }; }
wait_status_contains() {
  needle="$1"; out="$2"; i=0
  while [ "$i" -lt 30 ]; do
    if curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >"$out" 2>/dev/null && grep -F "$needle" "$out" >/dev/null; then return 0; fi
    i=$((i + 1)); sleep 1
  done
  echo "status did not contain: $needle" >&2; cat "$out" >&2 || true; return 1
}

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
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
require_json "$status" '"persistent_model_allowed":false' 'status semantics'
require_json "$status" '"external_transport_enabled":false' 'status semantics'
require_json "$status" '"accessibility":false' 'status semantics'
require_json "$status" '"notification_listener":false' 'status semantics'
echo 'STAGE_STATUS_SEMANTICS=PROVEN'

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No kernel listener found for Companion port' >&2; adb shell ss -ltn >&2 || true; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener is not visibly loopback-bound' >&2; printf '%s\n' "$listen" >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion control plane is wildcard-bound' >&2; exit 1; fi
echo 'STAGE_KERNEL_LOOPBACK=PROVEN'

code=$(curl -sS -o /tmp/hakim-proof-action.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${ACTION_REQUEST_ID}" -H 'Content-Type: application/json' -d '{"action":"local_proof"}' "${BASE_URL}/v1/action")
[ "$code" = '200' ] || fail_http 'local proof action' 200 "$code" /tmp/hakim-proof-action.json
grep -F '"ok":true' /tmp/hakim-proof-action.json >/dev/null
sleep 1
code=$(curl -sS -o /tmp/hakim-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
[ "$code" = '200' ] || fail_http 'owned browser UI' 200 "$code" /tmp/hakim-ui.json
grep -F 'hakim-proof-button' /tmp/hakim-ui.json >/dev/null || { cat /tmp/hakim-ui.json >&2; exit 1; }
grep -F 'hakim-proof-input' /tmp/hakim-ui.json >/dev/null || { cat /tmp/hakim-ui.json >&2; exit 1; }
echo 'STAGE_OWNED_BROWSER_UI=PROVEN'

code=$(curl -sS -o /tmp/hakim-screenshot.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/screenshot")
[ "$code" = '200' ] || fail_http 'owned browser screenshot' 200 "$code" /tmp/hakim-screenshot.json
python3 - <<'PY'
import base64,json
with open('/tmp/hakim-screenshot.json',encoding='utf-8') as f: obj=json.load(f)
data=base64.b64decode(obj['png_base64'],validate=True)
assert len(data)>1000,len(data)
assert data.startswith(b'\x89PNG\r\n\x1a\n'),data[:8]
assert obj.get('mode')=='browser_view'
PY
echo 'STAGE_OWNED_BROWSER_SCREENSHOT=PROVEN'

code=$(curl -sS -o /tmp/hakim-action-replay.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${ACTION_REQUEST_ID}" -H 'Content-Type: application/json' -d '{"action":"local_proof"}' "${BASE_URL}/v1/action")
[ "$code" = '409' ] || fail_http 'action replay' 409 "$code" /tmp/hakim-action-replay.json
grep -F '"error":"duplicate_request"' /tmp/hakim-action-replay.json >/dev/null || { cat /tmp/hakim-action-replay.json >&2; exit 1; }
echo 'STAGE_ACTION_REPLAY_PROTECTION=PROVEN'

python3 - "$PAIR_TOKEN" <<'PY' >/tmp/hakim-task-uri.txt
import base64,hashlib,hmac,json,sys,time,urllib.parse
key=sys.argv[1].encode()
plan={
  'request_id':'emulator-signed-task-0001',
  'expires_at_ms':int(time.time()*1000)+60000,
  'steps':[
    {'action':'local_proof'},
    {'action':'wait','ms':800},
    {'action':'set_text','id':'hakim-proof-input','value':'نجح الاختبار'},
    {'action':'click_css','selector':'#hakim-proof-button'}
  ]
}
raw=json.dumps(plan,separators=(',',':'),ensure_ascii=False).encode()
b64=base64.urlsafe_b64encode(raw).decode().rstrip('=')
sig=hmac.new(key,('HAKIM-TASK-v1\n'+b64).encode(),hashlib.sha256).hexdigest()
print('hakim://task?'+urllib.parse.urlencode({'plan':b64,'sig':sig}))
PY
TASK_URI=$(cat /tmp/hakim-task-uri.txt)
adb shell am start -W -a android.intent.action.VIEW -d "$TASK_URI" "$PKG" >/dev/null
wait_status_contains 'completed:emulator-signed-task-0001' /tmp/hakim-signed-task-status.json
echo 'STAGE_SIGNED_TASK_EXECUTION=PROVEN'

adb shell am start -W -a android.intent.action.VIEW -d "$TASK_URI" "$PKG" >/dev/null
wait_status_contains 'task_duplicate' /tmp/hakim-signed-task-replay.json
echo 'STAGE_SIGNED_TASK_REPLAY_REJECTION=PROVEN'

BAD_URI="${TASK_URI%????????????????????????????????????????????????????????????????}0000000000000000000000000000000000000000000000000000000000000000"
adb shell am start -W -a android.intent.action.VIEW -d "$BAD_URI" "$PKG" >/dev/null
wait_status_contains 'task_bad_signature' /tmp/hakim-signed-task-badsig.json
echo 'STAGE_SIGNED_TASK_BAD_SIGNATURE_REJECTION=PROVEN'

python3 - "$PAIR_TOKEN" <<'PY' >/tmp/hakim-expired-task-uri.txt
import base64,hashlib,hmac,json,sys,time,urllib.parse
key=sys.argv[1].encode()
plan={'request_id':'emulator-expired-task-0001','expires_at_ms':int(time.time()*1000)-1000,'steps':[{'action':'local_proof'}]}
raw=json.dumps(plan,separators=(',',':')).encode(); b64=base64.urlsafe_b64encode(raw).decode().rstrip('=')
sig=hmac.new(key,('HAKIM-TASK-v1\n'+b64).encode(),hashlib.sha256).hexdigest()
print('hakim://task?'+urllib.parse.urlencode({'plan':b64,'sig':sig}))
PY
EXPIRED_URI=$(cat /tmp/hakim-expired-task-uri.txt)
adb shell am start -W -a android.intent.action.VIEW -d "$EXPIRED_URI" "$PKG" >/dev/null
wait_status_contains 'task_expired_or_too_far' /tmp/hakim-signed-task-expired.json
echo 'STAGE_SIGNED_TASK_EXPIRY_REJECTION=PROVEN'

code=$(curl -sS -o /tmp/hakim-launch-missing-id.json -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '400' ] || fail_http 'bounded launch missing request identity' 400 "$code" /tmp/hakim-launch-missing-id.json
code=$(curl -sS -o /tmp/hakim-launch.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${LAUNCH_REQUEST_ID}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '200' ] || fail_http 'bounded launch' 200 "$code" /tmp/hakim-launch.json
grep -F '"ok":true' /tmp/hakim-launch.json >/dev/null
echo 'STAGE_BOUNDED_LAUNCH=PROVEN'

adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-restart.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane did not recover after process death' >&2; exit 1; }; sleep 1
done
require_json "$(cat /tmp/hakim-status-after-restart.json)" '"external_transport_enabled":false' 'restart status'
if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then echo 'Unexpected resident local-model process' >&2; exit 1; fi
echo 'STAGE_PROCESS_RECOVERY=PROVEN'

adb reboot
adb wait-for-device
boot=''; i=0
while [ "$i" -lt 90 ]; do boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r'); [ "$boot" = '1' ] && break; i=$((i + 1)); sleep 2; done
[ "$boot" = '1' ]
adb shell pm path "$PKG" | grep '^package:'
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}"
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-reboot.json 2>/dev/null; do i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Authenticated control plane did not recover after reboot' >&2; exit 1; }; sleep 1; done
require_json "$(cat /tmp/hakim-status-after-reboot.json)" '"evidence_state":"NOT_PROVEN"' 'reboot status'
require_json "$(cat /tmp/hakim-status-after-reboot.json)" '"persistent_model_allowed":false' 'reboot status'
require_json "$(cat /tmp/hakim-status-after-reboot.json)" '"external_transport_enabled":false' 'reboot status'

echo 'EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_PAIRING=SCAFFOLD_ONLY'
echo 'EMULATOR_AUTH_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_LOOPBACK_BINDING=PROVEN'
echo 'EMULATOR_STATUS_SEMANTICS=PROVEN'
echo 'EMULATOR_OWNED_BROWSER_UI=PROVEN'
echo 'EMULATOR_OWNED_BROWSER_SCREENSHOT=PROVEN'
echo 'EMULATOR_ACTION_REPLAY_PROTECTION=PROVEN'
echo 'EMULATOR_SIGNED_TASK_EXECUTION=PROVEN'
echo 'EMULATOR_SIGNED_TASK_BAD_SIGNATURE_REJECTION=PROVEN'
echo 'EMULATOR_SIGNED_TASK_REPLAY_REJECTION=PROVEN'
echo 'EMULATOR_SIGNED_TASK_EXPIRY_REJECTION=PROVEN'
echo 'EMULATOR_PROCESS_RECOVERY=PROVEN'
echo 'EMULATOR_PAIRING_RECOVERY=PROVEN'
echo 'EMULATOR_CONTROL_PLANE=PROVEN'
echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN'
