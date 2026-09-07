#!/system/bin/sh
# Disposable Android 15 emulator qualification for Notification Listener semantics.
# This is pre-field evidence only. It never grants permissions on a physical device
# and never replaces Android Human Gates on the owned TECNO/HiOS target.
set -eu

PKG="org.hakim.omega.companion"
LISTENER="${PKG}/.HakimNotificationListener"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"
TITLE="HAKIM_EMULATOR_NOTIFICATION_PROBE"
TEXT="notification-listener-event-observed"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-status-pre.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane unavailable for notification gate' >&2; exit 1; }; sleep 1
done

# Precondition: no listener authority should be assumed merely because the app is running.
if grep -F '"notification_listener":true' /tmp/hakim-notification-status-pre.json >/dev/null; then
  echo 'Notification Listener unexpectedly connected before emulator-only grant' >&2
  cat /tmp/hakim-notification-status-pre.json >&2
  exit 1
fi
code=$(curl -sS -o /tmp/hakim-notifications-pre.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications before listener grant' 409 "$code" /tmp/hakim-notifications-pre.json
grep -F '"error":"notification_listener_unavailable"' /tmp/hakim-notifications-pre.json >/dev/null || { cat /tmp/hakim-notifications-pre.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_FAIL_CLOSED_PRE_GRANT=PROVEN'

# CI-emulator-only authority grant. Physical-device permission remains a Human Gate.
adb shell cmd notification allow_listener "$LISTENER"
i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-status-connected.json 2>/dev/null && grep -F '"notification_listener":true' /tmp/hakim-notification-status-connected.json >/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Notification Listener did not connect after emulator-only grant' >&2; cat /tmp/hakim-notification-status-connected.json >&2 || true; adb shell cmd notification listeners >&2 || true; exit 1; }; sleep 1
done
echo 'STAGE_NOTIFICATION_LISTENER_CONNECTED=PROVEN'

# Generate a real Android notification from the shell package and require the listener
# event to cross the authenticated loopback API with observable payload evidence.
adb shell cmd notification post -S bigtext -t "$TITLE" hakim-emulator-probe "$TEXT" >/dev/null
i=0
while [ "$i" -lt 30 ]; do
  code=$(curl -sS -o /tmp/hakim-notifications-event.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
  if [ "$code" = '200' ] && grep -F "$TITLE" /tmp/hakim-notifications-event.json >/dev/null && grep -F "$TEXT" /tmp/hakim-notifications-event.json >/dev/null; then
    break
  fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 30 ] || { echo 'Notification event was not observed through Companion API' >&2; cat /tmp/hakim-notifications-event.json >&2 || true; exit 1; }
grep -F '"package":"com.android.shell"' /tmp/hakim-notifications-event.json >/dev/null || { echo 'Notification event lacks expected source package' >&2; cat /tmp/hakim-notifications-event.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_EVENT_OBSERVED=PROVEN'

# Revocation must become visible and fail closed; stale event history must not make
# an unavailable listener look healthy.
adb shell cmd notification disallow_listener "$LISTENER"
i=0
while [ "$i" -lt 30 ]; do
  curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-status-revoked.json 2>/dev/null || true
  if grep -F '"notification_listener":false' /tmp/hakim-notification-status-revoked.json >/dev/null 2>&1; then break; fi
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 30 ] || { echo 'Notification Listener revocation was not reflected in status' >&2; cat /tmp/hakim-notification-status-revoked.json >&2 || true; exit 1; }
code=$(curl -sS -o /tmp/hakim-notifications-revoked.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications after listener revocation' 409 "$code" /tmp/hakim-notifications-revoked.json
grep -F '"error":"notification_listener_unavailable"' /tmp/hakim-notifications-revoked.json >/dev/null || { cat /tmp/hakim-notifications-revoked.json >&2; exit 1; }
echo 'STAGE_NOTIFICATION_REVOCATION_FAIL_CLOSED=PROVEN'

echo 'EMULATOR_NOTIFICATION_LISTENER=PROVEN'
echo 'PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_PROVEN'
