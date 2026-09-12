#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"
PAIR_TOKEN_FILE="$OMEGA/hakim-companion-pair-token"
LOCAL_PORT=48765

[ -f "$CFG" ] && [ -s "$PAIR_TOKEN_FILE" ] || { echo 'ERROR: HAKIM bootstrap state missing.' >&2; exit 2; }
TARGET="$(python - "$CFG" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8')).get('adb_target',''))
PY
)"
[ -n "$TARGET" ] || { echo 'ERROR: adb_target missing.' >&2; exit 3; }
adb -s "$TARGET" get-state 2>/dev/null | grep -qx device || { echo 'ERROR: maintenance ADB is not connected.' >&2; exit 4; }
PAIR_TOKEN="$(cat "$PAIR_TOKEN_FILE")"
adb -s "$TARGET" forward --remove "tcp:$LOCAL_PORT" >/dev/null 2>&1 || true
adb -s "$TARGET" forward "tcp:$LOCAL_PORT" tcp:47651 >/dev/null
STATUS="$(curl -fsS --max-time 5 -H "Authorization: Bearer $PAIR_TOKEN" "http://127.0.0.1:$LOCAL_PORT/v1/status")" || { echo 'ERROR: Companion loopback status unavailable; keep maintenance bridge open.' >&2; exit 5; }

python - "$STATUS" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
missing=[]
if not x.get('control_server_listening'): missing.append('control_server')
if not x.get('accessibility'): missing.append('accessibility')
if not x.get('notification_listener'): missing.append('notification_listener')
if missing:
    raise SystemExit('ERROR: Companion not ready; keep ADB open. Missing: '+','.join(missing))
print('✅ Companion local readiness verified before maintenance shutdown.')
PY

# First prove the Developer-options master setting can be written and read back
# while the maintenance transport is still alive. Wireless ADB is disabled last,
# because that action may intentionally destroy the very channel used to inspect it.
echo 'إغلاق وضع الصيانة؛ التشغيل المعتاد سيبقى عبر Companion فقط...'
adb -s "$TARGET" shell settings put global development_settings_enabled 0 >/dev/null
DEV="$(adb -s "$TARGET" shell settings get global development_settings_enabled 2>/dev/null | tr -d '\r')"
[ "$DEV" = '0' ] || { echo "ERROR: Developer Options readback is '$DEV', expected 0; maintenance bridge retained." >&2; exit 6; }

# Request both ADB channels off. Loss of the connection after this point is an
# expected positive effect, but it is NOT by itself proof of Companion autonomy.
adb -s "$TARGET" shell 'settings put global adb_enabled 0; settings put global adb_wifi_enabled 0' >/dev/null 2>&1 || true
sleep 2

python - "$CFG" <<'PY'
import json,sys,os,tempfile,time
from pathlib import Path
p=Path(sys.argv[1]); d=json.loads(p.read_text(encoding='utf-8'))
d['maintenance_close_requested_at_ms']=int(time.time()*1000)
d['developer_options_readback_before_transport_close']='0'
d['normal_runtime']='android-companion'
d['adb_target_last']=d.get('adb_target','')
d['adb_target']=''
d['maintenance_close_state']='REQUESTED_AWAITING_COMPANION_ONLY_ROUND_TRIP'
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=str(p.parent)); os.close(fd)
Path(tmp).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); os.chmod(tmp,0o600); os.replace(tmp,p)
PY

adb forward --remove "tcp:$LOCAL_PORT" >/dev/null 2>&1 || true
printf '%s\n' \
  '✅ HAKIM_ADB_MAINTENANCE_CLOSE_REQUESTED' \
  '✅ Developer Options=0 تم التحقق منها قبل إسقاط قناة الصيانة.' \
  '⏳ لا يُرفع CLOSED_VERIFIED إلا بعد نجاح جولة Companion بعيدة مستقلة بلا ADB.'
