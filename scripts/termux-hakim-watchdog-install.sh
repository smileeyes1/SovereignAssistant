#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# HAKIM Termux Watchdog Bootstrap
# Purpose: keep the already-installed Hakim app nudged toward recovery without
# ADB/root, secrets, remote shell, package replacement, or permission escalation.
# This is a helper only; Hakim's authenticated HC1/HR1 relay remains authoritative.

PKG="ps.hakim.stable"
HOME_DIR="${HOME}/.hakim-watchdog"
BIN_DIR="${HOME}/bin"
BOOT_DIR="${HOME}/.termux/boot"
LOG="${HOME_DIR}/watchdog.log"
STATE="${HOME_DIR}/state"
INTERVAL="${HAKIM_WATCHDOG_INTERVAL:-300}"

case "$INTERVAL" in *[!0-9]*|'') INTERVAL=300;; esac
if [ "$INTERVAL" -lt 60 ]; then INTERVAL=60; fi
if [ "$INTERVAL" -gt 1800 ]; then INTERVAL=1800; fi

mkdir -p "$HOME_DIR" "$BIN_DIR" "$BOOT_DIR"
umask 077

cat > "$BIN_DIR/hakim-watchdog" <<'WATCHDOG'
#!/data/data/com.termux/files/usr/bin/bash
set -u
PKG="ps.hakim.stable"
HOME_DIR="${HOME}/.hakim-watchdog"
LOG="${HOME_DIR}/watchdog.log"
STATE="${HOME_DIR}/state"
INTERVAL="${HAKIM_WATCHDOG_INTERVAL:-300}"
case "$INTERVAL" in *[!0-9]*|'') INTERVAL=300;; esac
[ "$INTERVAL" -lt 60 ] && INTERVAL=60
[ "$INTERVAL" -gt 1800 ] && INTERVAL=1800
mkdir -p "$HOME_DIR"; umask 077
exec 9>"${HOME_DIR}/lock"
command -v flock >/dev/null 2>&1 && flock -n 9 || exit 0
log(){ printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; tail -n 200 "$LOG" > "${LOG}.tmp" 2>/dev/null && mv "${LOG}.tmp" "$LOG" || true; }
installed(){ /system/bin/pm path "$PKG" >/dev/null 2>&1; }
nudge(){
  # Safe, public Android launch only. No force-stop, no data clear, no ADB/root.
  /system/bin/monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
}
backoff=5
log "watchdog_start"
while :; do
  if installed; then
    printf 'installed\n' > "$STATE"
    # Do not repeatedly foreground Hakim. Only nudge after boot/start or after a
    # prior missing state; the app's own recovery/foreground service owns relay continuity.
    if [ ! -f "${HOME_DIR}/nudged" ]; then nudge; : > "${HOME_DIR}/nudged"; log "hakim_nudged_once"; fi
    backoff=5
    sleep "$INTERVAL"
  else
    printf 'missing\n' > "$STATE"; rm -f "${HOME_DIR}/nudged"; log "hakim_package_missing"
    sleep "$backoff"; backoff=$((backoff * 2)); [ "$backoff" -gt 300 ] && backoff=300
  fi
done
WATCHDOG
chmod 700 "$BIN_DIR/hakim-watchdog"

cat > "$BOOT_DIR/hakim-watchdog" <<'BOOT'
#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot executes this after Android boot once the companion is installed/enabled.
export PATH="${HOME}/bin:/data/data/com.termux/files/usr/bin:/system/bin"
mkdir -p "${HOME}/.hakim-watchdog"
nohup "${HOME}/bin/hakim-watchdog" >/dev/null 2>&1 &
BOOT
chmod 700 "$BOOT_DIR/hakim-watchdog"

# Start now, idempotently. Existing watchdog exits via flock.
nohup "$BIN_DIR/hakim-watchdog" >/dev/null 2>&1 &
printf '%s\n' "HAKIM_WATCHDOG_INSTALLED"
printf '%s\n' "package=$PKG"
printf '%s\n' "interval_seconds=$INTERVAL"
printf '%s\n' "state=$STATE"
printf '%s\n' "No ADB/root/secrets/remote-shell/package replacement was used."
printf '%s\n' "For automatic post-reboot start, Android must allow the official Termux:Boot companion once."
