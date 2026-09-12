#!/system/bin/sh
# Disposable Android 15 emulator gate for local control during Android airplane mode.
# This is pre-field evidence only and never qualifies physical TECNO/HiOS behavior.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"

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

# Force process death while airplane mode is active, then require purely local
# authenticated loopback recovery. adb forwarding is transport for the CI probe,
# not a Companion runtime dependency. Android can transiently delay process
# visibility after connectivity changes; readiness is the gate, not an instant race.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null

i=0
while [ "$i" -lt 15 ]; do
  if adb shell pidof "$PKG" >/dev/null 2>&1; then break; fi
  i=$((i + 1)); sleep 1
done
if [ "$i" -ge 15 ]; then
  echo 'Companion process did not become visible after airplane-mode restart' >&2
  adb shell dumpsys activity activities | grep -F "$PKG" >&2 || true
  adb logcat -d -t 250 | grep -E "${PKG}|AndroidRuntime|FATAL EXCEPTION" >&2 || true
  exit 1
fi
echo 'STAGE_AIRPLANE_PROCESS_VISIBLE=PROVEN'

adb forward --remove "tcp:${PORT}" >/dev/null 2>&1 || true
adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-airplane-status.json 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo 'Local authenticated control plane did not recover in airplane mode' >&2
    adb shell ss -ltn 2>/dev/null | grep ":${PORT}" >&2 || true
    adb shell dumpsys activity services "$PKG" >&2 || true
    adb logcat -d -t 250 | grep -E "${PKG}|AndroidRuntime|FATAL EXCEPTION" >&2 || true
    exit 1
  fi
  sleep 1
done
status=$(cat /tmp/hakim-airplane-status.json)
printf '%s' "$status" | grep -F '"loopback_only":true' >/dev/null
printf '%s' "$status" | grep -F '"control_server_listening":true' >/dev/null
printf '%s' "$status" | grep -F '"persistent_model_allowed":false' >/dev/null
printf '%s' "$status" | grep -F '"evidence_state":"NOT_PROVEN"' >/dev/null

listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ] || { echo 'No Companion listener while airplane mode active' >&2; exit 1; }
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null || { echo 'Companion listener lost loopback binding in airplane mode' >&2; exit 1; }
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then echo 'Companion became wildcard-bound in airplane mode' >&2; exit 1; fi

if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process during airplane-mode recovery' >&2
  exit 1
fi

echo 'EMULATOR_AIRPLANE_LOCAL_CONTROL=PROVEN'
echo 'EMULATOR_AIRPLANE_PROCESS_RECOVERY=PROVEN'
echo 'PHYSICAL_TECNO_OFFLINE_FIELD_QUALIFICATION=NOT_PROVEN'
