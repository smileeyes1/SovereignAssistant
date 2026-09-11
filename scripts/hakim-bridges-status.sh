#!/data/data/com.termux/files/usr/bin/bash
set -u
OMEGA="$HOME/.omega"
STATE="$OMEGA/hakim-multibridge-state.json"
CONFIG="$OMEGA/hakim-termux-adb.json"

echo '=== HAKIM BRIDGES ==='
if [ -f "$STATE" ]; then
  cat "$STATE"
else
  echo '{"status":"no_supervisor_state_yet"}'
fi

echo
printf 'supervisor='; tmux has-session -t hakim-multibridge-supervisor 2>/dev/null && echo running || echo stopped
printf 'relay_worker='; tmux has-session -t hakim-relay-worker 2>/dev/null && echo running || echo stopped
printf 'control_window='; if [ -s "$OMEGA/hakim-control-until" ] && [ "$(cat "$OMEGA/hakim-control-until" 2>/dev/null || echo 0)" -gt "$(date +%s%3N)" ] 2>/dev/null; then echo open; else echo closed; fi
if [ -f "$CONFIG" ]; then
  python - "$CONFIG" <<'PY'
import json,sys
try:
 d=json.load(open(sys.argv[1],encoding='utf-8'))
 print('adb_target='+str(d.get('adb_target','')))
 print('transport='+str(d.get('transport','')))
 print('apk_required='+str(d.get('apk_required',False)).lower())
except Exception as e:
 print('config_error='+type(e).__name__)
PY
fi
