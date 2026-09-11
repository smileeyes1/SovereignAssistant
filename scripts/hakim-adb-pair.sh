#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PAIR_ADDR="${1:-}"
PAIR_CODE="${2:-}"
CONNECT_ADDR="${3:-}"
OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"
BRIDGE="$OMEGA/bin/hakim-termux-adb-bridge.py"

if [[ ! "$PAIR_ADDR" =~ ^[0-9a-fA-F:.]+:[0-9]{2,5}$ ]]; then
  echo 'الاستخدام: hakim-adb-pair IP:PAIR_PORT PAIR_CODE [IP:CONNECT_PORT]' >&2
  exit 2
fi
if [[ ! "$PAIR_CODE" =~ ^[0-9]{6}$ ]]; then
  echo 'ERROR: pairing code must be 6 digits' >&2
  exit 2
fi
[ -f "$CFG" ] || { echo 'ERROR: run bootstrap-hakim-termux-adb.sh first' >&2; exit 3; }

printf '%s\n' "$PAIR_CODE" | adb pair "$PAIR_ADDR" >/tmp/hakim-adb-pair.out 2>/tmp/hakim-adb-pair.err || {
  cat /tmp/hakim-adb-pair.err >&2
  exit 4
}
cat /tmp/hakim-adb-pair.out
sleep 2

if [ -z "$CONNECT_ADDR" ]; then
  CONNECT_ADDR="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}')"
fi
if [ -z "$CONNECT_ADDR" ]; then
  echo 'PAIRED_BUT_CONNECT_ENDPOINT_NOT_DISCOVERED'
  echo 'أرسل لقطة شاشة صفحة «التصحيح اللاسلكي» الرئيسية لإكمال الاتصال.'
  exit 5
fi

adb connect "$CONNECT_ADDR" >/tmp/hakim-adb-connect.out 2>/tmp/hakim-adb-connect.err || true
cat /tmp/hakim-adb-connect.out
if ! adb -s "$CONNECT_ADDR" get-state 2>/dev/null | grep -qx device; then
  cat /tmp/hakim-adb-connect.err >&2 || true
  echo 'ERROR: paired but adb connection is not active' >&2
  exit 6
fi

python - "$CONNECT_ADDR" <<'PY'
import json,sys
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
d=json.loads(p.read_text())
d['adb_target']=sys.argv[1]
p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
p.chmod(0o600)
PY

tmux kill-session -t hakim-adb-bridge 2>/dev/null || true
tmux new-session -d -s hakim-adb-bridge "python '$BRIDGE'"
"$OMEGA/bin/hakim-control-window" 60 >/dev/null
sleep 1

echo '✅ HAKIM_ADB_PAIRED_AND_LIVE'
echo "TARGET=$CONNECT_ADDR"
adb -s "$CONNECT_ADDR" shell getprop ro.product.manufacturer | tr -d '\r'
adb -s "$CONNECT_ADDR" shell getprop ro.product.model | tr -d '\r'
