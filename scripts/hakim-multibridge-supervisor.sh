#!/data/data/com.termux/files/usr/bin/bash
set -u

OMEGA="$HOME/.omega"
CONFIG="$OMEGA/hakim-termux-adb.json"
BRIDGE="$OMEGA/bin/hakim-termux-adb-bridge.py"
STATE="$OMEGA/hakim-multibridge-state.json"
LOG="$OMEGA/hakim-multibridge-supervisor.log"
INTERVAL="${HAKIM_SUPERVISOR_INTERVAL:-20}"
WORKER_SESSION="hakim-relay-worker"

mkdir -p "$OMEGA"
chmod 700 "$OMEGA"

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s %s\n' "$(stamp)" "$*" >> "$LOG"; }

read_target() {
  python - "$CONFIG" <<'PY' 2>/dev/null
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    print(d.get('adb_target',''))
except Exception:
    print('')
PY
}

write_target() {
  python - "$CONFIG" "$1" <<'PY'
import json,sys,os,tempfile
p,target=sys.argv[1:]
try: d=json.load(open(p,encoding='utf-8'))
except Exception: d={}
d['adb_target']=target
d['transport']='termux-wireless-adb'
d['apk_required']=False
fd,tmp=tempfile.mkstemp(prefix='.hakim-cfg-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
}

adb_online() {
  local target="$1"
  [ -n "$target" ] && adb -s "$target" get-state 2>/dev/null | grep -qx device
}

discover_target() {
  adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}'
}

ensure_worker() {
  if ! tmux has-session -t "$WORKER_SESSION" 2>/dev/null; then
    tmux new-session -d -s "$WORKER_SESSION" "python '$BRIDGE'"
    log 'relay_worker_started'
  fi
}

stop_worker() {
  if tmux has-session -t "$WORKER_SESSION" 2>/dev/null; then
    tmux kill-session -t "$WORKER_SESSION" 2>/dev/null || true
    log 'relay_worker_stopped_adb_offline'
  fi
}

write_state() {
  local target="$1" adb_state="$2" worker_state="$3" action="$4"
  TARGET="$target" ADB_STATE="$adb_state" WORKER_STATE="$worker_state" LAST_ACTION="$action" python - "$STATE" <<'PY'
import json,os,sys,time,tempfile
p=sys.argv[1]
d={
 'updated_at_ms':int(time.time()*1000),
 'transport':'termux-wireless-adb',
 'adb_target':os.environ.get('TARGET',''),
 'adb':os.environ.get('ADB_STATE','offline'),
 'relay_worker':os.environ.get('WORKER_STATE','stopped'),
 'github_relay':'configured',
 'make_relay':'fallback-configured',
 'remote_desktop_commander':'external-maintenance-bridge',
 'result_mailbox':'configured',
 'last_action':os.environ.get('LAST_ACTION',''),
}
fd,tmp=tempfile.mkstemp(prefix='.hakim-state-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
}

termux-wake-lock >/dev/null 2>&1 || true

while true; do
  action='none'
  target="$(read_target)"

  if ! adb_online "$target"; then
    found="$(discover_target)"
    if [ -n "$found" ]; then
      adb connect "$found" >/dev/null 2>&1 || true
      if adb_online "$found"; then
        target="$found"
        write_target "$target"
        action='adb_reconnected_via_mdns'
        log "adb_reconnected target=$target"
      fi
    fi
  fi

  if adb_online "$target"; then
    ensure_worker
    write_state "$target" 'device' 'running' "$action"
  else
    stop_worker
    write_state "$target" 'offline' 'stopped' "$action"
  fi

  sleep "$INTERVAL"
done
