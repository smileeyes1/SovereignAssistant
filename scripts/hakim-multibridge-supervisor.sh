#!/data/data/com.termux/files/usr/bin/bash
set -u

OMEGA="$HOME/.omega"
CONFIG="$OMEGA/hakim-termux-adb.json"
STATE="$OMEGA/hakim-multibridge-state.json"
LOG="$OMEGA/hakim-multibridge-supervisor.log"
LAST_REPORT="$OMEGA/hakim-supervisor-last-report"
INTERVAL="${HAKIM_SUPERVISOR_INTERVAL:-20}"
LEGACY_PUBLIC_WORKER_SESSION="hakim-relay-worker"
LOCAL_DEV_GUARD="$OMEGA/bin/hakim-dev-mode-guardian.sh"
REMOTE_DEV_GUARD="/data/local/tmp/hakim-dev-mode-guardian.sh"
REMOTE_DEV_FLAG="/data/local/tmp/hakim-dev-mode-guardian.enabled"
REMOTE_DEV_PID="/data/local/tmp/hakim-dev-mode-guardian.pid"

mkdir -p "$OMEGA"
chmod 700 "$OMEGA"

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s %s\n' "$(stamp)" "$*" >> "$LOG"; }

read_config_field() {
  local field="$1"
  python - "$CONFIG" "$field" <<'PY' 2>/dev/null
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    v=d.get(sys.argv[2],'')
    print(v if isinstance(v,str) else '')
except Exception:
    print('')
PY
}

read_config_bool() {
  local field="$1"
  python - "$CONFIG" "$field" <<'PY' 2>/dev/null
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    print('1' if d.get(sys.argv[2]) is True else '0')
except Exception:
    print('0')
PY
}

read_target() { read_config_field adb_target; }
read_result_url() { read_config_field result_url; }

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

discover_target_mdns() {
  adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/ {print $NF; exit}'
}

ensure_dev_guardian() {
  local target="$1" p
  [ "$(read_config_bool developer_master_off_wireless_adb_on_field_verified)" = 1 ] || return 0
  [ -f "$LOCAL_DEV_GUARD" ] || { log 'dev_guardian_local_source_missing'; return 0; }
  adb_online "$target" || return 0

  if ! adb -s "$target" shell "[ -x '$REMOTE_DEV_GUARD' ]" >/dev/null 2>&1; then
    adb -s "$target" push "$LOCAL_DEV_GUARD" "$REMOTE_DEV_GUARD" >/dev/null 2>&1 || { log 'dev_guardian_push_failed'; return 0; }
    adb -s "$target" shell chmod 700 "$REMOTE_DEV_GUARD" >/dev/null 2>&1 || true
  fi

  adb -s "$target" shell touch "$REMOTE_DEV_FLAG" >/dev/null 2>&1 || true
  if ! adb -s "$target" shell "p=\$(cat '$REMOTE_DEV_PID' 2>/dev/null); [ -n \"\$p\" ] && kill -0 \"\$p\" 2>/dev/null" >/dev/null 2>&1; then
    adb -s "$target" shell "rm -f '$REMOTE_DEV_PID'; if command -v nohup >/dev/null 2>&1; then nohup sh '$REMOTE_DEV_GUARD' >/dev/null 2>&1 </dev/null & else sh '$REMOTE_DEV_GUARD' >/dev/null 2>&1 </dev/null & fi" >/dev/null 2>&1 || true
    sleep 1
    if adb -s "$target" shell "p=\$(cat '$REMOTE_DEV_PID' 2>/dev/null); [ -n \"\$p\" ] && kill -0 \"\$p\" 2>/dev/null" >/dev/null 2>&1; then
      log 'dev_guardian_restarted'
    else
      log 'dev_guardian_restart_failed'
    fi
  fi
}

# Result telemetry is OUTBOUND ONLY. It carries no pairing code, password,
# token, command, or user content. Failure never blocks local operation.
post_transition_result() {
  local target="$1" adb_state="$2" action="$3"
  local url key previous payload
  url="$(read_result_url)"
  [[ "$url" =~ ^https:// ]] || return 0
  key="$adb_state|$action|$target"
  previous="$(cat "$LAST_REPORT" 2>/dev/null || true)"
  [ "$key" = "$previous" ] && return 0
  payload="$(TARGET="$target" ADB_STATE="$adb_state" LAST_ACTION="$action" python - <<'PY'
import json,os,time
now=int(time.time()*1000)
print(json.dumps({
  'request_id': f'hakim-supervisor-{now}',
  'status': 'ok' if os.environ.get('ADB_STATE') == 'device' else 'degraded',
  'received_at_ms': now,
  'result': {
    'source': 'hakim-multibridge-supervisor',
    'adb': os.environ.get('ADB_STATE','offline'),
    'action': os.environ.get('LAST_ACTION','none'),
    'target': os.environ.get('TARGET',''),
  }
},separators=(',',':')))
PY
)"
  if curl -fsS -m 5 -H 'Content-Type: application/json' --data-binary "$payload" "$url" >/dev/null 2>&1; then
    printf '%s' "$key" > "$LAST_REPORT"
    chmod 600 "$LAST_REPORT" 2>/dev/null || true
  else
    log 'result_telemetry_failed'
  fi
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
    # Highest-value recovery first: retry the last verified endpoint. This
    # survives adb disconnect / server restart when mDNS discovery is flaky.
    if [ -n "$target" ]; then
      adb connect "$target" >/dev/null 2>&1 || true
      if adb_online "$target"; then
        action='adb_reconnected_saved_target'
        log "adb_reconnected_saved target=$target"
      fi
    fi
  fi

  if ! adb_online "$target"; then
    found="$(discover_target_mdns)"
    if [ -n "$found" ]; then
      adb connect "$found" >/dev/null 2>&1 || true
      if adb_online "$found"; then
        target="$found"
        write_target "$target"
        action='adb_reconnected_via_mdns'
        log "adb_reconnected_mdns target=$target"
      fi
    fi
  fi

  # Reassert fail-closed policy every cycle in case an older boot/session tries
  # to resurrect the retired public worker.
  stop_legacy_public_worker
  if adb_online "$target"; then
    ensure_dev_guardian "$target"
    write_state "$target" 'device' "$action"
    post_transition_result "$target" 'device' "$action"
  else
    write_state "$target" 'offline' "$action"
    post_transition_result "$target" 'offline' "$action"
  fi

  sleep "$INTERVAL"
done
