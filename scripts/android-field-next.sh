#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"
OUT="$ROOT/.omega/device-field-profile.json"
CFG="$HOME/.omega/hakim-termux-adb.json"
mkdir -p "$(dirname "$OUT")"

getprop_safe() {
  getprop "$1" 2>/dev/null | tr -d '\r'
}

background_json='{"status":"NOT_PROVEN","reason":"hakim-android unavailable"}'
if command -v hakim-android >/dev/null 2>&1; then
  background_json="$(hakim-android background-test status 2>/dev/null || printf '%s' '{"status":"ERROR"}')"
fi

mem_kb="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || true)"
mem_kb="${mem_kb:-0}"
avail_kb="$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {print $4; exit}')"
avail_kb="${avail_kb:-0}"
cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 0)"
termux_release="$(termux-info 2>/dev/null | awk -F= '/^TERMUX_APP__APK_RELEASE=/{print $2; exit}')"
termux_version="$(termux-info 2>/dev/null | awk -F= '/^TERMUX_VERSION=/{print $2; exit}')"

adb_state='UNPAIRED'
adb_target=''
if [ -f "$CFG" ]; then
  adb_target="$(python - "$CFG" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1],encoding='utf-8')).get('adb_target',''))
except Exception: print('')
PY
)"
  if [ -n "$adb_target" ] && command -v adb >/dev/null 2>&1 && adb -s "$adb_target" get-state 2>/dev/null | grep -qx device; then
    adb_state='CONNECTED'
  fi
fi

# Current sovereign sequence:
# 1) qualify the real phone through the governing Termux Wireless ADB path;
# 2) only after FIELD evidence, qualify Companion as a no-ADB normal-runtime candidate;
# 3) promote/retire ADB only after a real Companion-only round trip succeeds.
if [ "$adb_state" = 'CONNECTED' ]; then
  next_gate='TERMUX_ADB_REAL_FIELD_ROUND_TRIP'
else
  next_gate='ANDROID_WIRELESS_DEBUGGING_PAIRING'
fi

BACKGROUND_JSON="$background_json" \
MANUFACTURER="$(getprop_safe ro.product.manufacturer)" \
BRAND="$(getprop_safe ro.product.brand)" \
MODEL="$(getprop_safe ro.product.model)" \
DEVICE="$(getprop_safe ro.product.device)" \
ANDROID_RELEASE="$(getprop_safe ro.build.version.release)" \
ANDROID_SDK="$(getprop_safe ro.build.version.sdk)" \
ABI="$(getprop_safe ro.product.cpu.abi)" \
MEM_KB="$mem_kb" AVAIL_KB="$avail_kb" CORES="$cores" \
TERMUX_RELEASE="$termux_release" TERMUX_VERSION="$termux_version" \
ADB_STATE="$adb_state" ADB_TARGET="$adb_target" NEXT_GATE="$next_gate" \
OUT="$OUT" python - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
try:
    background = json.loads(os.environ['BACKGROUND_JSON'])
except Exception:
    background = {'status': 'ERROR', 'reason': 'invalid background status JSON'}
mem_kb = int(float(os.environ.get('MEM_KB') or 0))
avail_kb = int(float(os.environ.get('AVAIL_KB') or 0))
payload = {
    'captured_at': datetime.now(timezone.utc).isoformat(),
    'device': {
        'manufacturer': os.environ.get('MANUFACTURER', ''),
        'brand': os.environ.get('BRAND', ''),
        'model': os.environ.get('MODEL', ''),
        'device': os.environ.get('DEVICE', ''),
        'android_release': os.environ.get('ANDROID_RELEASE', ''),
        'android_sdk': os.environ.get('ANDROID_SDK', ''),
        'abi': os.environ.get('ABI', ''),
        'cpu_cores': int(os.environ.get('CORES') or 0),
        'ram_gib': round(mem_kb / 1024 / 1024, 2),
        'home_available_gib': round(avail_kb / 1024 / 1024, 2),
        'termux_apk_release': os.environ.get('TERMUX_RELEASE', ''),
        'termux_version': os.environ.get('TERMUX_VERSION', ''),
    },
    'field_path': 'TERMUX_WIRELESS_ADB_LOCAL',
    'adb_state': os.environ['ADB_STATE'],
    'adb_target': os.environ['ADB_TARGET'],
    'background_survival': background,
    'background_survival_role': 'diagnostic_until_real_field_matrix',
    'next_gate': os.environ['NEXT_GATE'],
    'post_field_candidate': 'ANDROID_COMPANION_NO_ADB_RUNTIME',
    'promotion_rule': 'Never retire ADB or claim Companion primary until physical FIELD and a Companion-only real round trip are both proven.',
    'model_selection_policy': (
        'Local inference is optional and on-demand only after core device qualification; '
        'never keep a resident local model and never use a local LLM for autonomous planning.'
    ),
}
out = Path(os.environ['OUT'])
tmp = out.with_name('.' + out.name + '.tmp')
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
os.replace(tmp, out)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
