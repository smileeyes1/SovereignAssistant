#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PAIR_ADDR="${1:-}"
PAIR_CODE="${2:-}"
CONNECT_ADDR="${3:-}"
ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"

if [[ ! "$PAIR_ADDR" =~ ^[0-9a-fA-F:.]+:[0-9]{2,5}$ ]]; then
  echo 'الاستخدام: hakim-field-start IP:PAIR_PORT PAIR_CODE [IP:CONNECT_PORT]' >&2
  exit 2
fi
if [[ ! "$PAIR_CODE" =~ ^[0-9]{6}$ ]]; then
  echo 'ERROR: pairing code must be 6 digits' >&2
  exit 2
fi
[ -d "$ROOT/.git" ] || { echo 'ERROR: HAKIM source repository is missing.' >&2; exit 3; }

cd "$ROOT"
git pull --ff-only

# FIELD must remain private. If the local config is absent, bootstrap only from
# secrets already supplied in the local environment; never embed or print them.
if [ ! -f "$CFG" ]; then
  [ -n "${HAKIM_RELAY_TOPIC:-}" ] && [ -n "${HAKIM_RESULT_URL:-}" ] && [ -n "${HAKIM_RELAY_KEY:-}" ] || {
    echo 'ERROR: private relay config missing. Restore the local HAKIM config or provide the three private environment variables together.' >&2
    exit 4
  }
  OMEGA_ROOT="$ROOT" bash "$ROOT/scripts/bootstrap-hakim-termux-adb.sh" \
    "$HAKIM_RELAY_TOPIC" "$HAKIM_RESULT_URL" "$HAKIM_RELAY_KEY"
fi

python - "$CFG" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
if x.get('public_command_transport') is not False:
    raise SystemExit('ERROR: public command transport is forbidden')
if x.get('upstream_bridges') != ['make-private-relay']:
    raise SystemExit('ERROR: active upstream must be make-private-relay only')
for k in ('topic','result_url','relay_key'):
    if not x.get(k): raise SystemExit('ERROR: private config is incomplete: '+k)
PY

pkg install -y python android-tools tmux curl git >/dev/null
mkdir -p "$OMEGA/bin"
chmod 700 "$OMEGA" "$OMEGA/bin"
for f in hakim-termux-adb-bridge.py hakim-adb-pair.sh hakim-control-window.sh hakim-multibridge-supervisor.sh hakim-bridges-status.sh; do
  [ -f "$ROOT/scripts/$f" ] || { echo "ERROR: missing $f" >&2; exit 5; }
done
cp -f "$ROOT/scripts/hakim-termux-adb-bridge.py" "$OMEGA/bin/hakim-termux-adb-bridge.py"
cp -f "$ROOT/scripts/hakim-adb-pair.sh" "$OMEGA/bin/hakim-adb-pair"
cp -f "$ROOT/scripts/hakim-control-window.sh" "$OMEGA/bin/hakim-control-window"
cp -f "$ROOT/scripts/hakim-multibridge-supervisor.sh" "$OMEGA/bin/hakim-multibridge-supervisor"
cp -f "$ROOT/scripts/hakim-bridges-status.sh" "$OMEGA/bin/hakim-bridges-status"
chmod 700 "$OMEGA/bin/"*
ln -sfn "$OMEGA/bin/hakim-adb-pair" "$PREFIX/bin/hakim-adb-pair"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-window"
ln -sfn "$OMEGA/bin/hakim-control-window" "$PREFIX/bin/hakim-control-on"
ln -sfn "$OMEGA/bin/hakim-bridges-status" "$PREFIX/bin/hakim-bridges-status"

printf '%s\n' '① تنفيذ الاقتران المحلي الذي يفرضه أندرويد...'
if [ -n "$CONNECT_ADDR" ]; then
  bash "$ROOT/scripts/hakim-adb-pair.sh" "$PAIR_ADDR" "$PAIR_CODE" "$CONNECT_ADDR"
else
  bash "$ROOT/scripts/hakim-adb-pair.sh" "$PAIR_ADDR" "$PAIR_CODE"
fi

printf '%s\n' '② التحقق من الجسر الخاص والمشرف الذاتي...'
hakim-bridges-status

printf '%s\n' '③ تسجيل الخطوة الميدانية التالية دون ترقية مبكرة...'
OMEGA_ROOT="$ROOT" bash "$ROOT/scripts/android-field-next.sh" > "$OMEGA/hakim-field-next.json"
chmod 600 "$OMEGA/hakim-field-next.json"

# Never auto-open mutating control. The remote matrix starts read-only. Any
# mutation still requires the explicit local time-bounded control window.
printf '%s\n' \
  '✅ HAKIM_FIELD_BRIDGE_READY' \
  '✅ القناة الخاصة والمشرف الذاتي جاهزان لاختبارات FIELD البعيدة.' \
  '🔒 نافذة أوامر التغيير بقيت مغلقة افتراضيًا.' \
  '⏭️ التالي: signed status round-trip ثم اختبارات الرفض/replay/expiry وباقي المصفوفة.'
