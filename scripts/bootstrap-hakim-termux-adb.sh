#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Backward-compatible input handling: an existing private result webhook may be
# supplied as the old second argument or directly as the first argument. Public
# relay topic/key inputs are intentionally ignored and never persisted.
ARG1="${1:-}"
ARG2="${2:-}"
RESULT_URL="${HAKIM_RESULT_URL:-}"
if [[ "$ARG2" =~ ^https:// ]]; then
  RESULT_URL="$ARG2"
elif [[ "$ARG1" =~ ^https:// ]]; then
  RESULT_URL="$ARG1"
fi
ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
OMEGA="$HOME/.omega"

if [[ -n "$RESULT_URL" && ! "$RESULT_URL" =~ ^https:// ]]; then
  echo 'ERROR: result URL must use HTTPS' >&2
  exit 2
fi
for f in scripts/hakim-adb-pair.sh scripts/hakim-control-window.sh scripts/hakim-multibridge-supervisor.sh scripts/hakim-bridges-status.sh; do
  [ -f "$ROOT/$f" ] || { echo "ERROR: HAKIM source missing: $f" >&2; exit 3; }
done

pkg install -y python android-tools tmux curl git >/dev/null
mkdir -p "$OMEGA/bin" "$HOME/.termux/boot"
chmod 700 "$OMEGA" "$OMEGA/bin"
cp -f "$ROOT/scripts/hakim-adb-pair.sh" "$OMEGA/bin/hakim-adb-pair"
cp -f "$ROOT/scripts/hakim-control-window.sh" "$OMEGA/bin/hakim-control-window"
cp -f "$ROOT/scripts/hakim-multibridge-supervisor.sh" "$OMEGA/bin/hakim-multibridge-supervisor"
cp -f "$ROOT/scripts/hakim-bridges-status.sh" "$OMEGA/bin/hakim-bridges-status"
chmod 700 "$OMEGA/bin/"*
ln -sfn "$OMEGA/bin/hakim-adb-pair" "$PREFIX/bin/hakim-adb-pair"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-window"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-on"
ln -sfn "$OMEGA/bin/hakim-bridges-status" "$PREFIX/bin/hakim-bridges-status"

# Retire the historical public-topic command worker from old installations.
# The governing supervisor also reasserts this fail-closed state continuously.
tmux kill-session -t hakim-relay-worker 2>/dev/null || true
rm -f "$OMEGA/bin/hakim-termux-adb-bridge.py"

RESULT_URL="$RESULT_URL" python - <<'PY'
import json, os, tempfile
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
try:
    old=json.loads(p.read_text(encoding='utf-8'))
except Exception:
    old={}
result_url=os.environ.get('RESULT_URL','').strip()
if not result_url:
    candidate=str(old.get('result_url','')).strip()
    if candidate.startswith('https://'):
        result_url=candidate
cfg={
 'result_url':result_url,
 'result_path_state':'configured' if result_url else 'pending_private_configuration',
 'adb_target':old.get('adb_target',''),
 'transport':'termux-wireless-adb',
 'apk_required':False,
 'upstream_bridges':['make-private-relay'],
 'make_private_command_relay':'required_unproven',
 'fallback_bridges':[],
 'public_command_transport':False,
 'public_github_command_relay':False,
 'legacy_public_relay_installed':False,
 'maintenance_bridges':['remote-desktop-commander'],
}
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=str(p.parent)); os.close(fd)
Path(tmp).write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8'); os.chmod(tmp,0o600); os.replace(tmp,p)
PY

# Optional reboot recovery: harmless without the separate Termux:Boot app.
cat > "$HOME/.termux/boot/99-hakim-multibridge" <<'SH'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock >/dev/null 2>&1 || true
sleep 8
tmux has-session -t hakim-multibridge-supervisor 2>/dev/null || tmux new-session -d -s hakim-multibridge-supervisor "$HOME/.omega/bin/hakim-multibridge-supervisor"
SH
chmod 700 "$HOME/.termux/boot/99-hakim-multibridge"

termux-wake-lock >/dev/null 2>&1 || true

# The supervisor owns local Wireless ADB reconnect only. It never opens the
# local mutating-control window and never starts the retired public worker.
tmux kill-session -t hakim-adb-bridge 2>/dev/null || true
tmux kill-session -t hakim-relay-worker 2>/dev/null || true
tmux kill-session -t hakim-multibridge-supervisor 2>/dev/null || true
tmux new-session -d -s hakim-multibridge-supervisor "$OMEGA/bin/hakim-multibridge-supervisor"

sleep 2
TARGET="$(python - <<'PY'
import json
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
try: print(json.loads(p.read_text()).get('adb_target',''))
except Exception: print('')
PY
)"
if [ -n "$TARGET" ] && adb -s "$TARGET" get-state 2>/dev/null | grep -qx device; then
  echo '✅ حكيم متصل ومشرف عليه ذاتيًا عبر التصحيح اللاسلكي المحلي.'
  hakim-bridges-status
  exit 0
fi

# Android intentionally requires a local user action for first wireless-debug pairing.
am start -a android.settings.WIRELESS_DEBUGGING_SETTINGS >/dev/null 2>&1 || \
am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS >/dev/null 2>&1 || true

echo '✅ تم تجهيز مسار حكيم المحلي بدون APK وبدون تجاوز Play Protect.'
echo '✅ النقل العام متقاعد، والمشرف يحافظ على Wireless ADB المحلي فقط.'
echo '🔐 بقي حاجز أندرويد الوحيد للمسار المحلي: الاقتران الأول بالتصحيح اللاسلكي.'
echo 'افتح «التصحيح اللاسلكي» واضغط «إقران الجهاز باستخدام رمز الإقران»، ثم أرسل لقطة الشاشة هنا.'
