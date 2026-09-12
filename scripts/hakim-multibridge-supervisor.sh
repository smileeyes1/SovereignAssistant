#!/data/data/com.termux/files/usr/bin/bash
set -u

OMEGA="$HOME/.omega"
CONFIG="$OMEGA/hakim-termux-adb.json"
STATE="$OMEGA/hakim-multibridge-state.json"
LOG="$OMEGA/hakim-multibridge-supervisor.log"
INTERVAL="${HAKIM_SUPERVISOR_INTERVAL:-20}"
LEGACY_PUBLIC_WORKER_SESSION="hakim-relay-worker"

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
d['public_command_transport']=False
d['upstream_bridges']=['make-private-relay']
d['fallback_bridges']=[]
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

# The historical relay worker consumes a public topic. The current sovereign
# contract forbids public command transport, so the supervisor must never
# start it and must actively stop any leftover session from an older release.
stop_legacy_public_worker() {
  if tmux has-session -t "$LEGACY_PUBLIC_WORKER_SESSION" 2>/dev/null; then
    tmux kill-session -t "$LEGACY_PUBLIC_WORKER_SESSION" 2>/dev/null || true
    log 'legacy_public_relay_worker_stopped_by_policy'
  fi
}

write_state() {
  local target="$1" adb_state="$2" action="$3"
  TARGET="$target" ADB_STATE="$adb_state" LAST_ACTION="$action" python - "$STATE" <<'PY'
import json,os,sys,time,tempfile
p=sys.argv[1]
d={
 'updated_at_ms':int(time.time()*1000),
 'transport':'termux-wireless-adb',
 'adb_target':os.environ.get('TARGET',''),
 'adb':os.environ.get('ADB_STATE','offline'),
 'public_command_transport':'disabled_by_sovereign_policy',
 'public_github_command_relay':'disabled',
 'legacy_public_relay_worker':'stopped',
 'make_private_command_relay':'required_unproven',
 'remote_desktop_commander':'optional_maintenance_only',
 'result_mailbox':'configured_result_path',
 'last_action':os.environ.get('LAST_ACTION',''),
}
fd,tmp=tempfile.mkstemp(prefix='.hakim-state-',dir=os.path.dirname(p) or '.')
os.close(fd)
with open(tmp,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
os.chmod(tmp,0o600); os.replace(tmp,p)
PY
}

termux-wake-lock >/dev/null 2>&1 || true
stop_legacy_public_worker

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

  # Reassert fail-closed policy every cycle in case an older boot/session tries
  # to resurrect the retired public worker.
  stop_legacy_public_worker
  if adb_online "$target"; then
    write_state "$target" 'device' "$action"
  else
    write_state "$target" 'offline' "$action"
  fi

  sleep "$INTERVAL"
done
