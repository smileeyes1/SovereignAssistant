#!/system/bin/sh
# Disposable Android 15 gate proving HAKIM local control and local proof while Android airplane mode is active.
# Pre-field evidence only; never qualifies physical-device behavior.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
RID="emulator-airplane-proof-0001"

restore_network() {
  adb shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
}
trap restore_network EXIT INT TERM

adb shell cmd connectivity airplane-mode enable >/dev/null
i=0
mode=''
while [ "$i" -lt 15 ]; do
  mode=$(adb shell settings get global airplane_mode_on 2>/dev/null | tr -d '\r')
  [ "$mode" = '1' ] && break
  i=$((i + 1)); sleep 1
done
[ "$mode" = '1' ] || { echo 'Android airplane mode did not become active' >&2; exit 1; }
echo 'STAGE_AIRPLANE_MODE_ACTIVE=PROVEN'

# Force process death while offline, then require purely local authenticated recovery.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-airplane-status.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Local authenticated control plane did not recover in airplane mode' >&2; exit 1; }; sleep 1
done
status=$(cat /tmp/hakim-airplane-status.json)
printf '%s' "$status" | grep -F '"loopback_only":true' >/dev/null
printf '%s' "$status" | grep -F '"control_server_listening":true' >/dev/null
printf '%s' "$status" | grep -F '"persistent_model_allowed":false' >/dev/null
printf '%s' "$status" | grep -F '"external_transport_enabled":false' >/dev/null
printf '%s' "$status" | grep -F '"attached":true' >/dev/null

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No Companion listener while airplane mode active' >&2; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener lost loopback binding in airplane mode' >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion became wildcard-bound in airplane mode' >&2; exit 1; fi

# Execute a no-network proof page inside the owned WebView while airplane mode is active.
PROOF='{"action":"local_proof","message":"نجح إثبات حكيم المحلي دون شبكة"}'
code=$(curl -sS -o /tmp/hakim-airplane-proof.json -w '%{http_code}' -H "$AUTH" -H "X-Hakim-Request-Id: ${RID}" -H 'Content-Type: application/json' -d "$PROOF" "${BASE_URL}/v1/action")
[ "$code" = '200' ] || { echo "offline local proof expected 200 got $code" >&2; cat /tmp/hakim-airplane-proof.json >&2; exit 1; }
grep -F '"ok":true' /tmp/hakim-airplane-proof.json >/dev/null
i=0
while [ "$i" -lt 20 ]; do
  code=$(curl -sS -o /tmp/hakim-airplane-ui.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/ui")
  if [ "$code" = '200' ] && grep -F 'hakim.local' /tmp/hakim-airplane-ui.json >/dev/null; then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 20 ] || { echo 'Offline local proof page was not observable' >&2; cat /tmp/hakim-airplane-ui.json >&2 || true; exit 1; }
echo 'STAGE_AIRPLANE_LOCAL_PROOF=PROVEN'

if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process during airplane-mode recovery' >&2
  exit 1
fi

echo 'EMULATOR_AIRPLANE_LOCAL_CONTROL=PROVEN'
echo 'EMULATOR_AIRPLANE_PROCESS_RECOVERY=PROVEN'
echo 'EMULATOR_AIRPLANE_ZERO_EXTERNAL_TRANSPORT=PROVEN'
echo 'EMULATOR_AIRPLANE_LOCAL_PROOF=PROVEN'
echo 'PHYSICAL_PHONE_OFFLINE_FIELD_QUALIFICATION=NOT_PROVEN'
