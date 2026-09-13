#!/system/bin/sh

FLAG=/data/local/tmp/hakim-dev-mode-guardian.enabled
PIDFILE=/data/local/tmp/hakim-dev-mode-guardian.pid
INTERVAL="${HAKIM_DEV_GUARD_INTERVAL:-8}"

umask 077
echo "$$" > "$PIDFILE"
cleanup() { rm -f "$PIDFILE"; }
trap cleanup EXIT INT TERM

while [ -f "$FLAG" ]; do
  dev="$(settings get global development_settings_enabled 2>/dev/null | tr -d '\r\n')"
  wifi="$(settings get global adb_wifi_enabled 2>/dev/null | tr -d '\r\n')"

  [ "$dev" = "0" ] || settings put global development_settings_enabled 0 >/dev/null 2>&1 || true
  [ "$wifi" = "1" ] || settings put global adb_wifi_enabled 1 >/dev/null 2>&1 || true

  sleep "$INTERVAL"
done

cleanup
