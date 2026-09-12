#!/system/bin/sh
# Android 15 emulator proof that the safe core does NOT register notification-listener authority.
# Pre-field evidence only; physical-device behavior remains unqualified.
set -eu

PKG="org.hakim.omega.companion"
PORT="47651"
PAIR_TOKEN="emulator-only-qualification-token-0123456789"
BASE_URL="http://127.0.0.1:${PORT}"
AUTH="Authorization: Bearer ${PAIR_TOKEN}"

fail_http() { echo "$1: expected HTTP $2 got $3" >&2; [ -f "$4" ] && cat "$4" >&2 || true; exit 1; }

adb forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null

i=0
until curl -fsS -H "$AUTH" "${BASE_URL}/v1/status" >/tmp/hakim-notification-safe-status.json 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { echo 'Companion control plane unavailable for notification safe-core gate' >&2; exit 1; }; sleep 1
done

grep -F '"notification_access":false' /tmp/hakim-notification-safe-status.json >/dev/null || { cat /tmp/hakim-notification-safe-status.json >&2; exit 1; }
if adb shell dumpsys package "$PKG" | grep -F 'HakimNotificationListener' >/dev/null; then
  echo 'Notification listener component unexpectedly registered in safe core' >&2
  exit 1
fi

code=$(curl -sS -o /tmp/hakim-notifications-safe.json -w '%{http_code}' -H "$AUTH" "${BASE_URL}/v1/notifications")
[ "$code" = '410' ] || fail_http 'safe-core notifications endpoint' 410 "$code" /tmp/hakim-notifications-safe.json
grep -F '"error":"disabled_in_safe_core"' /tmp/hakim-notifications-safe.json >/dev/null || { cat /tmp/hakim-notifications-safe.json >&2; exit 1; }
grep -F '"reason":"notification_access_not_registered"' /tmp/hakim-notifications-safe.json >/dev/null || { cat /tmp/hakim-notifications-safe.json >&2; exit 1; }

echo 'STAGE_NOTIFICATION_AUTHORITY_ABSENT=PROVEN'
echo 'STAGE_NOTIFICATION_ENDPOINT_FAIL_CLOSED=PROVEN'
echo 'EMULATOR_NOTIFICATION_LISTENER=NOT_REGISTERED_SAFE_CORE'
echo 'PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_APPLICABLE_SAFE_CORE'
