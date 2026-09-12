#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PAIR_ADDR="${1:-}"
PAIR_CODE="${2:-}"
CONNECT_ADDR="${3:-}"
OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"
SUPERVISOR="$OMEGA/bin/hakim-multibridge-supervisor"
INTERACTIVE=0

if [ "$PAIR_ADDR" = "--interactive" ]; then
  INTERACTIVE=1
  PAIR_ADDR=""
  PAIR_CODE=""
  CONNECT_ADDR=""
fi

[ -f "$CFG" ] || { echo 'ERROR: run bootstrap-hakim-termux-adb.sh first' >&2; exit 3; }

if [ "$INTERACTIVE" -eq 1 ]; then
  echo 'افتح «التصحيح اللاسلكي» ثم اضغط «إقران الجهاز باستخدام رمز الإقران».'
  echo 'سيكتشف حكيم عنوان الاقتران محليًا تلقائيًا؛ لن يرسل العنوان أو الرمز إلى أي خدمة.'
  for _ in $(seq 1 90); do
    PAIR_ADDR="$(adb mdns services 2>/dev/null | awk '/_adb-tls-pairing\._tcp/ {print $NF; exit}')"
    if [[ "$PAIR_ADDR" =~ ^[0-9a-fA-F:.]+:[0-9]{2,5}$ ]]; then
      break
    fi
    PAIR_ADDR=""
    sleep 2
  done
  if [ -z "$PAIR_ADDR" ]; then
    echo 'PAIRING_ENDPOINT_NOT_DISCOVERED_WITHIN_LIMIT' >&2
    echo 'أعد فتح نافذة «إقران الجهاز باستخدام رمز الإقران» ثم شغّل المسار مرة أخرى.' >&2
    exit 8
  fi
  printf 'أدخل رمز الاقتران ذي الستة أرقام ثم اضغط إدخال: '
  IFS= read -r PAIR_CODE
fi

if [[ ! "$PAIR_ADDR" =~ ^[0-9a-fA-F:.]+:[0-9]{2,5}$ ]]; then
  echo 'الاستخدام: hakim-adb-pair IP:PAIR_PORT PAIR_CODE [IP:CONNECT_PORT] أو hakim-adb-pair --interactive' >&2
  exit 2
fi
if [[ ! "$PAIR_CODE" =~ ^[0-9]{6}$ ]]; then
  echo 'ERROR: pairing code must be 6 digits' >&2
  exit 2
fi

printf '%s\n' "$PAIR_CODE" | adb pair "$PAIR_ADDR" >/tmp/hakim-adb-pair.out 2>/tmp/hakim-adb-pair.err || {
  cat /tmp/hakim-adb-pair.err >&2
  exit 4
}
PAIR_CODE=''
unset PAIR_CODE
cat /tmp/hakim-adb-pair.out
sleep 2

if [ -z "$CONNECT_ADDR" ]; then
  CONNECT_ADDR="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}')"
fi
if [ -z "$CONNECT_ADDR" ]; then
  echo 'PAIRED_BUT_CONNECT_ENDPOINT_NOT_DISCOVERED'
  echo 'أعد فتح صفحة «التصحيح اللاسلكي» الرئيسية ثم أعد المحاولة؛ الاقتران نفسه قد يكون محفوظًا.'
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
import json,sys,os,tempfile
from pathlib import Path
p=Path.home()/'.omega'/'hakim-termux-adb.json'
d=json.loads(p.read_text())
d['adb_target']=sys.argv[1]
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=str(p.parent)); os.close(fd)
Path(tmp).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); os.chmod(tmp,0o600); os.replace(tmp,p)
PY

# The supervisor owns reconnect. Mutating commands remain closed until the
# user explicitly opens a local control window with hakim-control-on.
tmux kill-session -t hakim-adb-bridge 2>/dev/null || true
tmux kill-session -t hakim-multibridge-supervisor 2>/dev/null || true
if [ -x "$SUPERVISOR" ]; then
  tmux new-session -d -s hakim-multibridge-supervisor "$SUPERVISOR"
else
  echo 'ERROR: multibridge supervisor is not installed; rerun bootstrap' >&2
  exit 7
fi
sleep 2

echo '✅ HAKIM_ADB_PAIRED_AND_SUPERVISED'
echo "TARGET=$CONNECT_ADDR"
echo '🔒 أوامر التغيير مغلقة افتراضيًا؛ افتح نافذة محلية فقط عند الحاجة: hakim-control-on 15'
adb -s "$CONNECT_ADDR" shell getprop ro.product.manufacturer | tr -d '\r'
adb -s "$CONNECT_ADDR" shell getprop ro.product.model | tr -d '\r'
