#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

OMEGA="$HOME/.omega"
ROOT="$OMEGA/hakim-live-src"
CFG="$OMEGA/hakim-termux-adb.json"

[[ -d /data/data/com.termux/files/usr ]] || { echo 'ERROR: TERMUX_REQUIRED' >&2; exit 2; }
[[ -f "$CFG" ]] || { echo 'ERROR: HAKIM_CONFIG_MISSING' >&2; exit 3; }

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

num_setting() {
  local t="$1" key="$2" v
  v="$(adb -s "$t" shell settings get global "$key" 2>/dev/null | tr -d '\r\n')"
  [[ "$v" =~ ^[0-9]+$ ]] || v=0
  printf '%s\n' "$v"
}

TARGET="$(read_target)"
if ! online "$TARGET"; then
  TARGET="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}')"
fi
if ! online "$TARGET"; then
  python "$ROOT/scripts/hakim-local-adb-recover.py" >/dev/null 2>&1 || true
  TARGET="$(read_target)"
fi
online "$TARGET" || { echo 'NO_GO: ADB_NOT_ONLINE'; exit 4; }

DEV_BEFORE="$(num_setting "$TARGET" development_settings_enabled)"
WIFI_BEFORE="$(num_setting "$TARGET" adb_wifi_enabled)"
USB_BEFORE="$(num_setting "$TARGET" adb_enabled)"
FINGERPRINT="$(adb -s "$TARGET" shell getprop ro.build.fingerprint 2>/dev/null | tr -d '\r\n')"

[[ "$WIFI_BEFORE" == 1 ]] || { echo 'NO_GO: WIRELESS_ADB_NOT_ENABLED'; exit 5; }

# Avoid Settings' own DeveloperOptions controllers. The UI master switch explicitly
# disables wireless ADB; this qualified path changes only the master visibility flag.
adb -s "$TARGET" shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1 || true
adb -s "$TARGET" shell am force-stop com.android.settings >/dev/null 2>&1 || true

ROLL="/data/local/tmp/hakim-dev-conceal-$$"
adb -s "$TARGET" shell "rm -f '$ROLL.commit'; (sleep 18; if [ ! -f '$ROLL.commit' ]; then settings put global development_settings_enabled '$DEV_BEFORE'; settings put global adb_wifi_enabled '$WIFI_BEFORE'; settings put global adb_enabled '$USB_BEFORE'; fi; rm -f '$ROLL.commit') >/dev/null 2>&1 </dev/null &" >/dev/null 2>&1

adb -s "$TARGET" shell settings put global development_settings_enabled 0 >/dev/null 2>&1 || true
sleep 4

PASS=0
if online "$TARGET"; then
  DEV_AFTER="$(num_setting "$TARGET" development_settings_enabled)"
  WIFI_AFTER="$(num_setting "$TARGET" adb_wifi_enabled)"
  if [[ "$DEV_AFTER" == 0 && "$WIFI_AFTER" == 1 ]]; then
    PASS=1
  fi
fi

if [[ "$PASS" == 1 ]]; then
  adb -s "$TARGET" shell touch "$ROLL.commit" >/dev/null 2>&1 || true
  python - "$CFG" "$TARGET" "$FINGERPRINT" <<'PY'
import json,sys,os,tempfile,time
p,target,fp=sys.argv[1:]
try: d=json.load(open(p,encoding='utf-8'))
except Exception: d={}
d['adb_target']=target
d['conceal_developer_options']=True
d['conceal_developer_options_field_verified']=True
d['conceal_qualified_fingerprint']=fp
d['conceal_verified_at_ms']=int(time.time()*1000)
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
  echo 'FIELD_VERIFIED_DEV_OPTIONS_CONCEALED_WITH_WIRELESS_ADB=PASS'
  echo "TARGET=$TARGET"
  echo 'developer_settings_enabled=0'
  echo 'adb_wifi_enabled=1'
  exit 0
fi

# Fail closed. If the link survived, restore immediately. If it dropped, the
# detached shell rollback above restores the exact previous settings after 18 s.
if online "$TARGET"; then
  adb -s "$TARGET" shell settings put global development_settings_enabled "$DEV_BEFORE" >/dev/null 2>&1 || true
  adb -s "$TARGET" shell settings put global adb_wifi_enabled "$WIFI_BEFORE" >/dev/null 2>&1 || true
  adb -s "$TARGET" shell settings put global adb_enabled "$USB_BEFORE" >/dev/null 2>&1 || true
else
  sleep 22
  python "$ROOT/scripts/hakim-local-adb-recover.py" >/dev/null 2>&1 || true
fi
python - "$CFG" <<'PY'
import json,sys,os,tempfile
p=sys.argv[1]
try: d=json.load(open(p,encoding='utf-8'))
except Exception: d={}
d['conceal_developer_options']=False
d['conceal_developer_options_field_verified']=False
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
echo 'FIELD_VERIFIED_DEV_OPTIONS_CONCEALED_WITH_WIRELESS_ADB=NO'
exit 6
