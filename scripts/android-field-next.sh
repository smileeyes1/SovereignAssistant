#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"
OUT="$ROOT/.omega/device-field-profile.json"
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
background_status = str(background.get('status', 'NOT_PROVEN'))
if background_status == 'PASS':
    next_gate = 'LOCAL_MODEL_SELECTION'
elif background_status in {'FAIL', 'ERROR'}:
    next_gate = 'BACKGROUND_SURVIVAL_REPAIR'
else:
    next_gate = 'BACKGROUND_SURVIVAL_EVIDENCE'

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
    'background_survival': background,
    'next_gate': next_gate,
    'model_selection_policy': 'Do not choose/download a local model until this exact profile is reviewed; use loopback-only inference and preserve offline-first constraints.',
}
out = Path(os.environ['OUT'])
tmp = out.with_name('.' + out.name + '.tmp')
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
os.replace(tmp, out)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
