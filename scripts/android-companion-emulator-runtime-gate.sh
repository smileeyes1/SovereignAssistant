#!/system/bin/sh
# POSIX-compatible Android emulator runtime qualification gate.
# This is pre-field evidence only; it never qualifies a physical TECNO/HiOS device.
set -eu

APK="android/hakim-companion/app/build/outputs/apk/debug/app-debug.apk"
PKG="org.hakim.omega.companion"

adb install -r "$APK"
adb shell pm path "$PKG" | grep '^package:'
adb shell am start -W -n "$PKG/.MainActivity"
adb shell dumpsys activity activities | grep -F "$PKG" >/dev/null

# Process death must not corrupt installability or relaunch.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity"
adb shell pidof "$PKG" >/dev/null

# The Companion must never package or spawn a resident local LLM.
if adb shell ps -A | grep -E 'llama-server|llama\.cpp'; then
  echo 'Unexpected resident local-model process' >&2
  exit 1
fi

# Reboot smoke: package and launcher remain recoverable after Android restart.
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

echo 'EMULATOR_RUNTIME=PROVEN'
echo 'PHYSICAL_TECNO_FIELD_QUALIFICATION=NOT_PROVEN'
