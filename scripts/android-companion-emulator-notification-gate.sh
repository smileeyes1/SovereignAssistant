#!/system/bin/sh
# Disposable Android 15 proof that the sovereign-local release has no notification-listener surface.
# Pre-field evidence only; never qualifies physical-device behavior.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
TITLE="HAKIM_EMULATOR_NOTIFICATION_PRIVACY_PROBE"
TEXT="must-not-be-readable-by-hakim"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-status.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane unavailable for notification privacy gate' >&2; exit 1; }; sleep 1
done
grep -F '"notification_listener":false' /tmp/hakim-notification-status.json >/dev/null || { cat /tmp/hakim-notification-status.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_LISTENER_ABSENT=PROVEN'

# The authenticated endpoint itself must fail closed and explicitly state that the listener is disabled.
code=$(curl -sS -o /tmp/hakim-notifications-disabled.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications disabled' 409 "$code" /tmp/hakim-notifications-disabled.json
grep -F 'notification_listener_disabled_by_play_protect_safe_mode' /tmp/hakim-notifications-disabled.json >/dev/null || { cat /tmp/hakim-notifications-disabled.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_ENDPOINT_FAIL_CLOSED=PROVEN'

# Create a real notification and prove the app still exposes no notification contents afterward.
adb shell cmd notification post -S bigtext -t "$TITLE" hakim-emulator-privacy-probe "$TEXT" >/dev/null
sleep 1
code=$(curl -sS -o /tmp/hakim-notifications-after-probe.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications remain disabled after system event' 409 "$code" /tmp/hakim-notifications-after-probe.json
if grep -F "$TITLE" /tmp/hakim-notifications-after-probe.json >/dev/null || grep -F "$TEXT" /tmp/hakim-notifications-after-probe.json >/dev/null; then
  echo 'Notification content leaked through disabled endpoint' >&2
  cat /tmp/hakim-notifications-after-probe.json >&2
  exit 1
fi
echo 'STAGE_NOTIFICATION_CONTENT_NONDISCLOSURE=PROVEN'

# Package metadata must not advertise an Android notification-listener service.
if adb shell dumpsys package "$PKG" | grep -F 'BIND_NOTIFICATION_LISTENER_SERVICE' >/dev/null; then
  echo 'Notification Listener permission unexpectedly present in installed package' >&2
  adb shell dumpsys package "$PKG" >&2
  exit 1
fi

echo 'EMULATOR_NOTIFICATION_LISTENER_ABSENT=PROVEN'
echo 'EMULATOR_NOTIFICATION_PRIVACY_FAIL_CLOSED=PROVEN'
echo 'PHYSICAL_PHONE_NOTIFICATION_PRIVACY_FIELD_QUALIFICATION=NOT_PROVEN'
