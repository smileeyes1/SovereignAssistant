#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PAIR_ADDR="${1:-}"
PAIR_CODE="${2:-}"
CONNECT_ADDR="${3:-}"
ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
CFG="$HOME/.omega/hakim-termux-adb.json"

if [[ ! "$PAIR_ADDR" =~ ^[0-9a-fA-F:.]+:[0-9]{2,5}$ ]]; then
  echo 'الاستخدام: hakim-field-start IP:PAIR_PORT PAIR_CODE [IP:CONNECT_PORT]' >&2
  exit 2
fi
if [[ ! "$PAIR_CODE" =~ ^[0-9]{6}$ ]]; then
  echo 'ERROR: pairing code must be 6 digits' >&2
  exit 2
fi

cd "$ROOT"
git pull --ff-only >/dev/null

# Refresh private transport configuration only from local environment variables.
# Secrets are never embedded in this public script/repository.
if [ -n "${HAKIM_RELAY_TOPIC:-}" ] || [ -n "${HAKIM_RESULT_URL:-}" ] || [ -n "${HAKIM_RELAY_KEY:-}" ]; then
  [ -n "${HAKIM_RELAY_TOPIC:-}" ] && [ -n "${HAKIM_RESULT_URL:-}" ] && [ -n "${HAKIM_RELAY_KEY:-}" ] || {
    echo 'ERROR: private relay environment must provide topic, result URL, and key together.' >&2; exit 3;
  }
  OMEGA_ROOT="$ROOT" bash "$ROOT/scripts/bootstrap-hakim-termux-adb.sh" \
    "$HAKIM_RELAY_TOPIC" "$HAKIM_RESULT_URL" "$HAKIM_RELAY_KEY"
fi

[ -f "$CFG" ] || { echo 'ERROR: private HAKIM config missing; refresh it before pairing.' >&2; exit 4; }

# Refuse stale/public transport configuration even if pairing itself would work.
python - "$CFG" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
if x.get('public_command_transport') is not False:
    raise SystemExit('ERROR: public/stale command transport is forbidden')
if x.get('upstream_bridges') != ['make-private-relay']:
    raise SystemExit('ERROR: Make private relay is not the active upstream bridge')
for k in ('topic','result_url','relay_key'):
    if not x.get(k): raise SystemExit('ERROR: missing private config '+k)
PY

echo '① اقتران أندرويد المحلي لمرة التأسيس/الصيانة...'
if [ -n "$CONNECT_ADDR" ]; then
  bash "$ROOT/scripts/hakim-adb-pair.sh" "$PAIR_ADDR" "$PAIR_CODE" "$CONNECT_ADDR"
else
  bash "$ROOT/scripts/hakim-adb-pair.sh" "$PAIR_ADDR" "$PAIR_CODE"
fi

echo '② من هنا يكمل حكيم تلقائيًا: تثبيت → تهيئة → موافقات محلية → إغلاق الصيانة.'
bash "$ROOT/scripts/hakim-complete-phone-bootstrap.sh"
