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
if [ ! -f "$ROOT/scripts/hakim-termux-adb-bridge.py" ]; then echo "ERROR: HAKIM source missing at $ROOT" >&2; exit 3; fi

pkg install -y python android-tools tmux curl git >/dev/null
mkdir -p "$OMEGA/bin"
chmod 700 "$OMEGA" "$OMEGA/bin"
cp -f "$ROOT/scripts/hakim-termux-adb-bridge.py" "$OMEGA/bin/hakim-termux-adb-bridge.py"
cp -f "$ROOT/scripts/hakim-adb-pair.sh" "$OMEGA/bin/hakim-adb-pair"
cp -f "$ROOT/scripts/hakim-control-window.sh" "$OMEGA/bin/hakim-control-window"
chmod 700 "$OMEGA/bin/"*
ln -sfn "$OMEGA/bin/hakim-adb-pair" "$PREFIX/bin/hakim-adb-pair"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-window"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-on"

TOPIC="$TOPIC" RESULT_URL="$RESULT_URL" RELAY_KEY="$RELAY_KEY" python - <<'PY'
import json, os
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
old={}
try: old=json.loads(p.read_text())
except Exception: pass
cfg={
 'topic':os.environ['TOPIC'],
 'result_url':os.environ['RESULT_URL'],
 'relay_key':os.environ['RELAY_KEY'],
 'adb_target':old.get('adb_target',''),
 'transport':'termux-wireless-adb',
 'apk_required':False,
}
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
p.chmod(0o600)
PY

termux-wake-lock >/dev/null 2>&1 || true

# If already paired, try to discover/connect and start without asking anything.
TARGET="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}')"
if [ -n "$TARGET" ]; then
  adb connect "$TARGET" >/dev/null 2>&1 || true
  if adb -s "$TARGET" get-state 2>/dev/null | grep -qx device; then
    python - "$TARGET" <<'PY'
import json,sys
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'; d=json.loads(p.read_text()); d['adb_target']=sys.argv[1]; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)); p.chmod(0o600)
PY
    tmux kill-session -t hakim-adb-bridge 2>/dev/null || true
    tmux new-session -d -s hakim-adb-bridge "python '$OMEGA/bin/hakim-termux-adb-bridge.py'"
    "$OMEGA/bin/hakim-control-window" 60 >/dev/null
    echo '✅ حكيم متصل عبر التصحيح اللاسلكي، والقناة الحية تعمل دون APK.'
    exit 0
  fi
fi

# Android intentionally requires a local user action for first wireless-debug pairing.
am start -a android.settings.WIRELESS_DEBUGGING_SETTINGS >/dev/null 2>&1 || \
am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS >/dev/null 2>&1 || true

echo '✅ تم تجهيز حكيم بدون APK وبدون تجاوز Play Protect.'
echo '🔐 بقي حاجز أندرويد الوحيد: الاقتران الأول بالتصحيح اللاسلكي.'
echo 'افتح «التصحيح اللاسلكي» واضغط «إقران الجهاز باستخدام رمز الإقران»، ثم أرسل لقطة الشاشة هنا.'
