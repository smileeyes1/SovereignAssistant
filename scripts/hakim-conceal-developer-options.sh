#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

OMEGA="$HOME/.omega"
ROOT="$OMEGA/hakim-live-src"
CFG="$OMEGA/hakim-termux-adb.json"
LOCAL_GUARD="$ROOT/scripts/hakim-dev-mode-guardian.sh"
REMOTE_GUARD="/data/local/tmp/hakim-dev-mode-guardian.sh"
REMOTE_FLAG="/data/local/tmp/hakim-dev-mode-guardian.enabled"
REMOTE_PID="/data/local/tmp/hakim-dev-mode-guardian.pid"

[[ -d /data/data/com.termux/files/usr ]] || { echo 'ERROR: TERMUX_REQUIRED' >&2; exit 2; }
[[ -f "$CFG" ]] || { echo 'ERROR: HAKIM_CONFIG_MISSING' >&2; exit 3; }
[[ -f "$LOCAL_GUARD" ]] || { echo 'ERROR: GUARDIAN_SOURCE_MISSING' >&2; exit 3; }

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

recover_target() {
  local t
  t="$(read_target)"
  if ! online "$t"; then
    t="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}')"
  fi
  if ! online "$t"; then
    python "$ROOT/scripts/hakim-local-adb-recover.py" >/dev/null 2>&1 || true
    t="$(read_target)"
  fi
  online "$t" || return 1
  printf '%s\n' "$t"
}

num_setting() {
  local t="$1" key="$2" v
  v="$(adb -s "$t" shell settings get global "$key" 2>/dev/null | tr -d '\r\n')"
  [[ "$v" =~ ^[0-9]+$ ]] || v=0
  printf '%s\n' "$v"
}

guardian_running() {
  local t="$1"
  adb -s "$t" shell "p=\$(cat '$REMOTE_PID' 2>/dev/null); [ -n \"\$p\" ] && kill -0 \"\$p\" 2>/dev/null" >/dev/null 2>&1
}

stop_guardian() {
  local t="$1"
  adb -s "$t" shell "rm -f '$REMOTE_FLAG'; p=\$(cat '$REMOTE_PID' 2>/dev/null); if [ -n \"\$p\" ] && [ -r /proc/\$p/cmdline ] && tr '\000' ' ' </proc/\$p/cmdline | grep -Fq 'hakim-dev-mode-guardian.sh'; then kill \"\$p\" 2>/dev/null || true; fi; rm -f '$REMOTE_PID'" >/dev/null 2>&1 || true
}

start_guardian() {
  local t="$1"
  adb -s "$t" push "$LOCAL_GUARD" "$REMOTE_GUARD" >/dev/null 2>&1 || return 1
  adb -s "$t" shell "chmod 700 '$REMOTE_GUARD'; touch '$REMOTE_FLAG'; p=\$(cat '$REMOTE_PID' 2>/dev/null); if [ -z \"\$p\" ] || ! kill -0 \"\$p\" 2>/dev/null; then rm -f '$REMOTE_PID'; if command -v nohup >/dev/null 2>&1; then nohup sh '$REMOTE_GUARD' >/dev/null 2>&1 </dev/null & else sh '$REMOTE_GUARD' >/dev/null 2>&1 </dev/null & fi; fi" >/dev/null 2>&1 || return 1
  sleep 2
  guardian_running "$t"
}

update_config_release() {
  python - "$CFG" <<'PY'
import json,sys,os,tempfile
p=sys.argv[1]
try: d=json.load(open(p,encoding='utf-8'))
except Exception: d={}
d['conceal_developer_options']=False
d['conceal_developer_options_field_verified']=False
d['developer_master_off_wireless_adb_on_field_verified']=False
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
}

TARGET="$(recover_target || true)"
online "$TARGET" || { echo 'NO_GO: ADB_NOT_ONLINE'; exit 4; }

if [[ "${1:-}" == "--release" ]]; then
  stop_guardian "$TARGET"
  adb -s "$TARGET" shell settings put global development_settings_enabled 1 >/dev/null 2>&1 || true
  adb -s "$TARGET" shell settings put global adb_wifi_enabled 1 >/dev/null 2>&1 || true
  sleep 2
  update_config_release
  echo 'HAKIM_DEV_MASTER_GUARD=RELEASED'
  echo "TARGET=$TARGET"
  exit 0
fi

DEV_BEFORE="$(num_setting "$TARGET" development_settings_enabled)"
WIFI_BEFORE="$(num_setting "$TARGET" adb_wifi_enabled)"
USB_BEFORE="$(num_setting "$TARGET" adb_enabled)"
FINGERPRINT="$(adb -s "$TARGET" shell getprop ro.build.fingerprint 2>/dev/null | tr -d '\r\n')"

[[ "$WIFI_BEFORE" == 1 ]] || { echo 'NO_GO: WIRELESS_ADB_NOT_ENABLED'; exit 5; }

# Do not use Settings' visible Developer Options master switch. Its controller
# explicitly disables wireless ADB. Leave Settings first, stop its process, then
# change only the underlying master flag while preserving ADB_WIFI_ENABLED=1.
adb -s "$TARGET" shell am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1 || true
adb -s "$TARGET" shell am force-stop com.android.settings >/dev/null 2>&1 || true

# Fail-safe is armed before the first mutation. If the transport drops before a
# verified commit, an already-running shell process disables the guardian and
# restores the exact prior values without needing a live adb client connection.
ROLL="/data/local/tmp/hakim-dev-master-roll-$$"
adb -s "$TARGET" shell "rm -f '$ROLL.commit'; (sleep 40; if [ ! -f '$ROLL.commit' ]; then rm -f '$REMOTE_FLAG'; settings put global development_settings_enabled '$DEV_BEFORE'; settings put global adb_wifi_enabled '$WIFI_BEFORE'; settings put global adb_enabled '$USB_BEFORE'; fi; rm -f '$ROLL.commit') >/dev/null 2>&1 </dev/null &" >/dev/null 2>&1

adb -s "$TARGET" shell settings put global development_settings_enabled 0 >/dev/null 2>&1 || true
sleep 4

PASS=0
if online "$TARGET"; then
  DEV_AFTER="$(num_setting "$TARGET" development_settings_enabled)"
  WIFI_AFTER="$(num_setting "$TARGET" adb_wifi_enabled)"
  if [[ "$DEV_AFTER" == 0 && "$WIFI_AFTER" == 1 ]] && start_guardian "$TARGET"; then
    # Prove the guardian, not just its process: perturb only the developer master
    # flag, then require autonomous return to 0 while wireless ADB remains online.
    adb -s "$TARGET" shell settings put global development_settings_enabled 1 >/dev/null 2>&1 || true
    sleep 10
    DEV_HEALED="$(num_setting "$TARGET" development_settings_enabled)"
    WIFI_HEALED="$(num_setting "$TARGET" adb_wifi_enabled)"
    if online "$TARGET" && guardian_running "$TARGET" && [[ "$DEV_HEALED" == 0 && "$WIFI_HEALED" == 1 ]]; then
      PASS=1
    fi
  fi
fi

if [[ "$PASS" == 1 ]]; then
  adb -s "$TARGET" shell touch "$ROLL.commit" >/dev/null 2>&1 || true
  python - "$CFG" "$TARGET" "$FINGERPRINT" "$DEV_BEFORE" "$WIFI_BEFORE" "$USB_BEFORE" <<'PY'
import json,sys,os,tempfile,time
p,target,fp,dev,wifi,usb=sys.argv[1:]
try: d=json.load(open(p,encoding='utf-8'))
except Exception: d={}
d['adb_target']=target
d['conceal_developer_options']=True
d['conceal_developer_options_field_verified']=True
d['developer_master_off_wireless_adb_on_field_verified']=True
d['conceal_qualified_fingerprint']=fp
d['developer_settings_before_conceal']=int(dev)
d['adb_wifi_before_conceal']=int(wifi)
d['adb_enabled_before_conceal']=int(usb)
d['conceal_verified_at_ms']=int(time.time()*1000)
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
  echo 'FIELD_VERIFIED_DEV_MASTER_OFF_WIRELESS_ADB_ON=PASS'
  echo 'DEV_MASTER_GUARD_SELF_HEAL=PASS'
  echo "TARGET=$TARGET"
  echo 'development_settings_enabled=0'
  echo 'adb_wifi_enabled=1'
  exit 0
fi

# Fail closed. Stop the guardian before restoring the previous master state.
if online "$TARGET"; then
  stop_guardian "$TARGET"
  adb -s "$TARGET" shell settings put global development_settings_enabled "$DEV_BEFORE" >/dev/null 2>&1 || true
  adb -s "$TARGET" shell settings put global adb_wifi_enabled "$WIFI_BEFORE" >/dev/null 2>&1 || true
  adb -s "$TARGET" shell settings put global adb_enabled "$USB_BEFORE" >/dev/null 2>&1 || true
else
  sleep 45
  python "$ROOT/scripts/hakim-local-adb-recover.py" >/dev/null 2>&1 || true
fi
update_config_release
echo 'FIELD_VERIFIED_DEV_MASTER_OFF_WIRELESS_ADB_ON=NO'
exit 6
