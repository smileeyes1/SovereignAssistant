#!/system/bin/sh
# POSIX-compatible Android emulator runtime qualification gate.
# This is pre-field evidence only; it never qualifies a physical TECNO/HiOS device.
# Runtime-only permissions may be granted to this disposable emulator so an OS dialog
# does not obscure lifecycle checks. Physical-device Human Gates remain untouched.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
# Avoid the Android 13+ notification prompt blocking lifecycle smoke in disposable CI.
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS
adb shell am start -W -n "$PKG/.MainActivity"
adb shell dumpsys activity activities | grep -F "$PKG" >/dev/null
adb shell pidof "$PKG" >/dev/null

# Pair only inside the disposable emulator. This token is non-secret test data and is
# intentionally unrelated to physical-device pairing or LOCAL_DEVICE_ONLY material.
adb shell am start -W -a android.intent.action.VIEW -d "hakim://pair?token=${PAIR_TOKEN}" "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}"

# Wait for the loopback control plane to be reachable through the ADB test tunnel.
i=0
until curl -fsS -H "Authorization: Bearer ${PAIR_TOKEN}" "${BASE_URL}/v1/status" >/tmp/hakim-status.json 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -lt 30 ] || { echo 'Companion control plane did not become ready' >&2; exit 1; }
  sleep 1
done

# Authentication must fail closed for missing and incorrect credentials.
code=$(curl -sS -o /tmp/hakim-missing-auth.json -w '%{http_code}' "${BASE_URL}/v1/status")
[ "$code" = '401' ]
code=$(curl -sS -o /tmp/hakim-wrong-auth.json -w '%{http_code}' -H 'Authorization: Bearer definitely-wrong-token' "${BASE_URL}/v1/status")
[ "$code" = '401' ]

# Authenticated status must report runtime facts without fabricating field evidence.
status=$(cat /tmp/hakim-status.json)
printf '%s' "$status" | grep -F '"evidence_state":"NOT_PROVEN"' >/dev/null
printf '%s' "$status" | grep -F '"loopback_only":true' >/dev/null
printf '%s' "$status" | grep -F '"control_server_listening":true' >/dev/null
printf '%s' "$status" | grep -F '"persistent_model":null' >/dev/null
printf '%s' "$status" | grep -F '"persistent_model_evidence":"NOT_PROVEN"' >/dev/null
printf '%s' "$status" | grep -F '"persistent_model_allowed":false' >/dev/null

# Prove the actual kernel socket is loopback-bound, not merely self-reported as such.
listen=$(adb shell ss -ltn 2>/dev/null | grep ":${PORT}" || true)
[ -n "$listen" ]
printf '%s\n' "$listen" | grep -E '127\.0\.0\.1|\[::1\]|::1' >/dev/null
if printf '%s\n' "$listen" | grep -E '0\.0\.0\.0|\[::\]:|:::47651' >/dev/null; then
  echo 'Companion control plane is wildcard-bound' >&2
  exit 1
fi

# Permission-gated capabilities must not silently succeed without Accessibility.
code=$(curl -sS -o /tmp/hakim-screenshot.json -w '%{http_code}' -H "Authorization: Bearer ${PAIR_TOKEN}" "${BASE_URL}/v1/screenshot")
[ "$code" = '409' ]
printf '%s' "$(cat /tmp/hakim-screenshot.json)" | grep -F '"error":"screenshot_unavailable"' >/dev/null
code=$(curl -sS -o /tmp/hakim-action.json -w '%{http_code}' -H "Authorization: Bearer ${PAIR_TOKEN}" -H 'Content-Type: application/json' -d '{"type":"back"}' "${BASE_URL}/v1/action")
[ "$code" = '409' ]
printf '%s' "$(cat /tmp/hakim-action.json)" | grep -F '"ok":false' >/dev/null

# A bounded safe launch request through the authenticated local service must work.
code=$(curl -sS -o /tmp/hakim-launch.json -w '%{http_code}' -H "Authorization: Bearer ${PAIR_TOKEN}" -H 'Content-Type: application/json' -d "{\"package\":\"${PKG}\"}" "${BASE_URL}/v1/launch")
[ "$code" = '200' ]
printf '%s' "$(cat /tmp/hakim-launch.json)" | grep -F '"ok":true' >/dev/null

# Process death must not corrupt installability, pairing, or authenticated relaunch.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity"
adb shell pidof "$PKG" >/dev/null
curl -fsS -H "Authorization: Bearer ${PAIR_TOKEN}" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-restart.json
printf '%s' "$(cat /tmp/hakim-status-after-restart.json)" | grep -F '"persistent_model_allowed":false' >/dev/null

# The Companion must never package or spawn a resident local LLM.
if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process' >&2
  exit 1
fi

# Reboot smoke: package, pairing, and authenticated local control remain recoverable.
adb reboot
adb wait-for-device
boot=''
i=0
while [ "$i" -lt 90 ]; do
  boot=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$boot" = '1' ] && break
  i=$((i + 1))
  sleep 2
done
[ "$boot" = '1' ]

adb shell pm path "$PKG" | grep '^package:'
adb shell am start -W -n "$PKG/.MainActivity"
adb shell pidof "$PKG" >/dev/null
adb forward "tcp:${PORT}" "tcp:${PORT}"
i=0
until curl -fsS -H "Authorization: Bearer ${PAIR_TOKEN}" "${BASE_URL}/v1/status" >/tmp/hakim-status-after-reboot.json 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -lt 30 ] || { echo 'Authenticated control plane did not recover after reboot' >&2; exit 1; }
  sleep 1
done
printf '%s' "$(cat /tmp/hakim-status-after-reboot.json)" | grep -F '"evidence_state":"NOT_PROVEN"' >/dev/null
printf '%s' "$(cat /tmp/hakim-status-after-reboot.json)" | grep -F '"persistent_model_allowed":false' >/dev/null

# A CI permission grant and emulator pairing are test scaffolding, never physical-device authority evidence.
echo 'EMULATOR_NOTIFICATION_PERMISSION=SCAFFOLD_ONLY'
echo 'EMULATOR_PAIRING=SCAFFOLD_ONLY'
echo 'EMULATOR_AUTH_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_LOOPBACK_BINDING=PROVEN'
echo 'EMULATOR_STATUS_SEMANTICS=PROVEN'
echo 'EMULATOR_PERMISSION_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_PAIRING_RECOVERY=PROVEN'
echo 'EMULATOR_CONTROL_PLANE=PROVEN'
echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN'
