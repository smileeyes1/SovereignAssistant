#!/system/bin/sh
# Android 15 emulator proof that notification-listener authority is registered but remains disabled
# until Android-local user enablement. Pre-field evidence only; physical-device behavior remains unqualified.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-status.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane unavailable for notification gate' >&2; exit 1; }; sleep 1
done

grep -F '"notification_access":false' /tmp/hakim-notification-status.json >/dev/null || { cat /tmp/hakim-notification-status.json >&2; exit 1; }
adb shell dumpsys package "$PKG" | grep -F 'HakimNotificationListener' >/dev/null || {
  echo 'Notification listener component is not registered' >&2
  exit 1
}

# Registration is not authority: without explicit Android-local user enablement the endpoint must fail closed.
code=$(curl -sS -o /tmp/hakim-notifications-disabled.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '409' ] || fail_http 'notifications before local user enablement' 409 "$code" /tmp/hakim-notifications-disabled.json
grep -F '"error":"notification_access_unavailable"' /tmp/hakim-notifications-disabled.json >/dev/null || { cat /tmp/hakim-notifications-disabled.json >&2; exit 1; }

# Never enable the listener through secure settings in CI; physical-device consent remains sovereign and local.
enabled=$(adb shell settings get secure enabled_notification_listeners 2>/dev/null | tr -d '\r' || true)
if printf '%s' "$enabled" | grep -F "$PKG" >/dev/null; then
  echo 'Notification listener became enabled without Android-local user action' >&2
  exit 1
fi

echo 'STAGE_NOTIFICATION_COMPONENT_REGISTERED=PROVEN'
echo 'STAGE_NOTIFICATION_USER_ENABLEMENT_REQUIRED=PROVEN'
echo 'STAGE_NOTIFICATION_ENDPOINT_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_NOTIFICATION_LISTENER=REGISTERED_DISABLED_BY_DEFAULT'
echo 'PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_PROVEN'
