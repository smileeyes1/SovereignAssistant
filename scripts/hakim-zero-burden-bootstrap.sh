#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ ! -d /data/data/com.termux/files/usr ]]; then
  echo 'ERROR: run inside Termux on the target Android phone.' >&2
  exit 2
fi

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
ROOT="${OMEGA_ROOT:-$HOME_DIR/.omega/hakim-live-src}"
OMEGA="$HOME_DIR/.omega"
BIN="$OMEGA/bin"
CFG="$OMEGA/hakim-termux-adb.json"
SUP="$BIN/hakim-multibridge-supervisor"
BOOT_DIR="$HOME_DIR/.termux/boot"
mkdir -p "$OMEGA" "$BIN" "$BOOT_DIR"
chmod 700 "$OMEGA" "$BIN" "$BOOT_DIR"

pkg install -y git python android-tools tmux curl >/dev/null

if [[ ! -d "$ROOT/.git" ]]; then
  git clone --depth 1 https://github.com/smileeyes1/SovereignAssistant.git "$ROOT"
else
  git -C "$ROOT" fetch origin main --prune
  git -C "$ROOT" checkout main
  git -C "$ROOT" pull --ff-only origin main
fi

for f in hakim-adb-pair.sh hakim-control-window.sh hakim-multibridge-supervisor.sh hakim-bridges-status.sh; do
  [[ -f "$ROOT/scripts/$f" ]] || { echo "ERROR: missing scripts/$f" >&2; exit 3; }
done

cp -f "$ROOT/scripts/hakim-adb-pair.sh" "$BIN/hakim-adb-pair"
cp -f "$ROOT/scripts/hakim-control-window.sh" "$BIN/hakim-control-window"
cp -f "$ROOT/scripts/hakim-multibridge-supervisor.sh" "$BIN/hakim-multibridge-supervisor"
cp -f "$ROOT/scripts/hakim-bridges-status.sh" "$BIN/hakim-bridges-status"
chmod 700 "$BIN/"*
ln -sfn "$BIN/hakim-adb-pair" "$PREFIX/bin/hakim-adb-pair"
ln -sfn "$BIN/hakim-control-window" "$PREFIX/bin/hakim-control-window"
ln -sfn "$BIN/hakim-control-window" "$PREFIX/bin/hakim-control-on"
ln -sfn "$BIN/hakim-bridges-status" "$PREFIX/bin/hakim-bridges-status"
ln -sfn "$ROOT/scripts/hakim-zero-burden-bootstrap.sh" "$PREFIX/bin/hakim-bootstrap"

# One stable local entry point. It never broadens authority: status is read-only,
# recover only restarts the local supervisor, and update runs the qualified
# bootstrap path with its own regression gates.
cat > "$BIN/hakim" <<'SH'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
OMEGA="$HOME/.omega"
SUP="$OMEGA/bin/hakim-multibridge-supervisor"
case "${1:-status}" in
  status)
    exec hakim-bridges-status
    ;;
  recover)
    tmux kill-session -t hakim-relay-worker 2>/dev/null || true
    tmux kill-session -t hakim-multibridge-supervisor 2>/dev/null || true
    tmux new-session -d -s hakim-multibridge-supervisor "$SUP"
    sleep 2
    exec hakim-bridges-status
    ;;
  update)
    exec hakim-bootstrap
    ;;
  *)
    echo 'الاستخدام: hakim [status|recover|update]'
    exit 2
    ;;
esac
SH
chmod 700 "$BIN/hakim"
ln -sfn "$BIN/hakim" "$PREFIX/bin/hakim"

# Reboot recovery is prepared once. Android still controls whether the optional
# Termux:Boot companion is installed/allowed; absence of it never weakens the
# foreground runtime and is not reported as a PASS.
cat > "$BOOT_DIR/99-hakim-multibridge" <<'SH'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock >/dev/null 2>&1 || true
sleep 8
SUP="$HOME/.omega/bin/hakim-multibridge-supervisor"
[ -x "$SUP" ] || exit 0
tmux has-session -t hakim-multibridge-supervisor 2>/dev/null || \
  tmux new-session -d -s hakim-multibridge-supervisor "$SUP"
SH
chmod 700 "$BOOT_DIR/99-hakim-multibridge"

# Ensure a config exists without overwriting any established result URL/target.
if [[ ! -f "$CFG" ]]; then
  cat > "$CFG" <<'JSON'
{
  "result_url": "",
  "result_path_state": "pending_private_configuration",
  "adb_target": "",
  "transport": "termux-wireless-adb",
  "apk_required": false,
  "public_command_transport": false,
  "public_github_command_relay": false,
  "legacy_public_relay_installed": false
}
JSON
  chmod 600 "$CFG"
fi

tmux kill-session -t hakim-relay-worker 2>/dev/null || true
tmux kill-session -t hakim-multibridge-supervisor 2>/dev/null || true
tmux new-session -d -s hakim-multibridge-supervisor "$SUP"

read_target() {
  python - "$CFG" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1],encoding='utf-8')).get('adb_target',''))
except Exception: print('')
PY
}

online() {
  local t="$1"
  [[ -n "$t" ]] && adb -s "$t" get-state 2>/dev/null | grep -qx device
}

wait_online() {
  local max="${1:-50}" i t
  for i in $(seq 1 "$max"); do
    t="$(read_target)"
    if online "$t"; then
      printf '%s\n' "$t"
      return 0
    fi
    sleep 2
  done
  return 1
}

TARGET="$(wait_online 20 || true)"
if [[ -z "$TARGET" ]]; then
  echo 'HAKIM_ZERO_BURDEN=PAIRING_REQUIRED'
  # Android requires a local user act for first pairing. Existing bootstrap
  # already minimizes this to the wireless-debugging screen + one 6-digit code.
  exec "$ROOT/scripts/bootstrap-hakim-termux-adb.sh"
fi

echo "HAKIM_ZERO_BURDEN=CONNECTED TARGET=$TARGET"

# Regression 1: disconnect transport only; pairing remains stored.
adb disconnect "$TARGET" >/dev/null 2>&1 || true
R1="$(wait_online 25 || true)"
if [[ -n "$R1" ]]; then
  echo 'RECONNECT_AFTER_DISCONNECT=PASS'
else
  echo 'RECONNECT_AFTER_DISCONNECT=FAIL'
fi

# Regression 2: restart adb server and require supervisor recovery.
adb kill-server >/dev/null 2>&1 || true
R2="$(wait_online 25 || true)"
if [[ -n "$R2" ]]; then
  echo 'RECONNECT_AFTER_KILL_SERVER=PASS'
else
  echo 'RECONNECT_AFTER_KILL_SERVER=FAIL'
fi

hakim-bridges-status || true

if [[ -n "$R1" && -n "$R2" ]]; then
  echo 'FIELD_VERIFIED_LOCAL_ADB_RECONNECT=PASS'
  exit 0
fi

echo 'FIELD_VERIFIED_LOCAL_ADB_RECONNECT=NO'
exit 4
