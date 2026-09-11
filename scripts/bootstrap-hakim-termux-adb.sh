#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TOPIC="${1:-${HAKIM_RELAY_TOPIC:-}}"
RESULT_URL="${2:-${HAKIM_RESULT_URL:-}}"
RELAY_KEY="${3:-${HAKIM_RELAY_KEY:-}}"
ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
OMEGA="$HOME/.omega"

if [[ ! "$TOPIC" =~ ^[A-Za-z0-9_-]{20,120}$ ]]; then echo 'ERROR: relay topic invalid' >&2; exit 2; fi
if [[ ! "$RESULT_URL" =~ ^https:// ]]; then echo 'ERROR: result URL invalid' >&2; exit 2; fi
if [[ ! "$RELAY_KEY" =~ ^[A-Za-z0-9_-]{40,100}$ ]]; then echo 'ERROR: relay key invalid' >&2; exit 2; fi
for f in scripts/hakim-termux-adb-bridge.py scripts/hakim-adb-pair.sh scripts/hakim-control-window.sh scripts/hakim-multibridge-supervisor.sh scripts/hakim-bridges-status.sh; do
  [ -f "$ROOT/$f" ] || { echo "ERROR: HAKIM source missing: $f" >&2; exit 3; }
done

pkg install -y python android-tools tmux curl git >/dev/null
mkdir -p "$OMEGA/bin" "$HOME/.termux/boot"
chmod 700 "$OMEGA" "$OMEGA/bin"
cp -f "$ROOT/scripts/hakim-termux-adb-bridge.py" "$OMEGA/bin/hakim-termux-adb-bridge.py"
cp -f "$ROOT/scripts/hakim-adb-pair.sh" "$OMEGA/bin/hakim-adb-pair"
cp -f "$ROOT/scripts/hakim-control-window.sh" "$OMEGA/bin/hakim-control-window"
cp -f "$ROOT/scripts/hakim-multibridge-supervisor.sh" "$OMEGA/bin/hakim-multibridge-supervisor"
cp -f "$ROOT/scripts/hakim-bridges-status.sh" "$OMEGA/bin/hakim-bridges-status"
chmod 700 "$OMEGA/bin/"*
ln -sfn "$OMEGA/bin/hakim-adb-pair" "$PREFIX/bin/hakim-adb-pair"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-window"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-on"
ln -sfn "$OMEGA/bin/hakim-bridges-status" "$PREFIX/bin/hakim-bridges-status"

TOPIC="$TOPIC" RESULT_URL="$RESULT_URL" RELAY_KEY="$RELAY_KEY" python - <<'PY'
import json, os, tempfile
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
try: old=json.loads(p.read_text())
except Exception: old={}
cfg={
 'topic':os.environ['TOPIC'],
 'result_url':os.environ['RESULT_URL'],
 'relay_key':os.environ['RELAY_KEY'],
 'adb_target':old.get('adb_target',''),
 'transport':'termux-wireless-adb',
 'apk_required':False,
 'upstream_bridges':['github-owner-relay','make-fallback'],
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

# The supervisor owns reconnect and relay-worker restart. It never opens the
# local mutating-control window automatically.
tmux kill-session -t hakim-adb-bridge 2>/dev/null || true
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
  echo '✅ حكيم متصل ومشرف عليه ذاتيًا عبر التصحيح اللاسلكي.'
  hakim-bridges-status
  exit 0
fi

# Android intentionally requires a local user action for first wireless-debug pairing.
am start -a android.settings.WIRELESS_DEBUGGING_SETTINGS >/dev/null 2>&1 || \
am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS >/dev/null 2>&1 || true

echo '✅ تم تجهيز منظومة جسور حكيم بدون APK وبدون تجاوز Play Protect.'
echo '✅ المشرف الذاتي يعمل ويعيد الاتصال ويعيد تشغيل العامل عند الحاجة.'
echo '🔐 بقي حاجز أندرويد الوحيد: الاقتران الأول بالتصحيح اللاسلكي.'
echo 'افتح «التصحيح اللاسلكي» واضغط «إقران الجهاز باستخدام رمز الإقران»، ثم أرسل لقطة الشاشة هنا.'
