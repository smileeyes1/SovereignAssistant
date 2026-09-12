#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ ! -d /data/data/com.termux/files/usr ]]; then
  echo 'ERROR: run inside Termux on the target Android phone.' >&2
  exit 2
fi

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
STATE_DIR="$HOME_DIR/.omega"
STATE="$STATE_DIR/phone-field-run.json"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${OMEGA_REPO:-$SCRIPT_REPO}"
if [[ ! -d "$REPO/.git" ]]; then
  REPO="${OMEGA_REPO:-$HOME_DIR/SovereignAssistant}"
fi

write_state() {
  local phase="$1"
  local detail="${2:-}"
  PHASE="$phase" DETAIL="$detail" STATE="$STATE" python - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ['STATE'])
old = {}
if path.exists():
    try:
        old = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        old = {}
payload = {
    'schema_version': '1.0',
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'phase': os.environ['PHASE'],
    'detail': os.environ.get('DETAIL',''),
    'field_verified': False,
    'promotion_allowed': False,
    'secrets_recorded': False,
    'attempts': int(old.get('attempts', 0)) + 1,
}
tmp = path.with_name('.' + path.name + '.tmp')
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
tmp.chmod(0o600)
tmp.replace(path)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

read_phase() {
  STATE="$STATE" python - <<'PY'
import json, os
from pathlib import Path
p=Path(os.environ['STATE'])
if not p.exists():
    print('NEW')
else:
    try:
        print(json.loads(p.read_text(encoding='utf-8')).get('phase','NEW'))
    except Exception:
        print('NEW')
PY
}

if [[ "${1:-}" == "--restart-install" ]]; then
  rm -f "$STATE"
fi

pkg install -y git curl python >/dev/null

if [[ ! -d "$REPO/.git" ]]; then
  git clone --depth 1 https://github.com/smileeyes1/SovereignAssistant.git "$REPO"
else
  git -C "$REPO" fetch origin main --prune
  git -C "$REPO" checkout main
  git -C "$REPO" pull --ff-only
fi

ln -sfn "$REPO/scripts/hakim-phone-field-run.sh" "$PREFIX/bin/hakim-phone-field"
chmod 700 "$REPO/scripts/hakim-phone-field-run.sh"

phase="$(read_phase)"

case "$phase" in
  NEW|REPO_REFRESHED)
    bash "$REPO/scripts/android-field-next.sh"
    if bash "$REPO/scripts/install-android-companion-local.sh"; then
      write_state "WAITING_ANDROID_INSTALL_APPROVAL" "Android Package Installer was prepared/opened; approve the local HAKIM Companion installation, then run hakim-phone-field again."
      cat <<'EOF'
HAKIM_PHONE_FIELD=WAITING_ANDROID_INSTALL_APPROVAL
أكمل موافقة Android على تثبيت HAKIM Companion فقط، ثم شغّل الأمر نفسه مرة أخرى:
hakim-phone-field
EOF
      exit 10
    else
      write_state "INSTALL_PREPARATION_FAILED" "Companion preparation/signing/install handoff failed."
      exit 20
    fi
    ;;

  WAITING_ANDROID_INSTALL_APPROVAL|WAITING_PAIR_OR_APP_OPEN|PAIR_RETRY_REQUIRED)
    if ! bash "$REPO/scripts/pair-android-companion.sh"; then
      write_state "WAITING_PAIR_OR_APP_OPEN" "Pair deep link could not be completed; confirm Companion is installed/open, then rerun."
      exit 11
    fi
    sleep 2
    if OMEGA_ROOT="$REPO" python "$REPO/scripts/android-physical-field-gate.py"; then
      write_state "PRE_FIELD_PASS" "Release provenance, local pairing, loopback controls and fail-closed preflight passed. Physical matrix remains NOT_PROVEN."
      cat <<'EOF'
HAKIM_PHONE_FIELD=PRE_FIELD_PASS
نجح التأهيل السابق للميدان. لم تُرفع FIELD_VERIFIED؛ تبقى مصفوفة الهاتف الحقيقية مطلوبة قبل الاعتماد الميداني الكامل.
EOF
      exit 0
    else
      write_state "PAIR_RETRY_REQUIRED" "Physical preflight did not pass yet; Companion may need to be opened or paired again."
      cat <<'EOF' >&2
HAKIM_PHONE_FIELD=PAIR_RETRY_REQUIRED
افتح HAKIM Companion على الهاتف إن لم يكن مفتوحًا، ثم شغّل:
hakim-phone-field
EOF
      exit 12
    fi
    ;;

  PRE_FIELD_PASS)
    if OMEGA_ROOT="$REPO" python "$REPO/scripts/android-physical-field-gate.py"; then
      write_state "PRE_FIELD_PASS" "Pre-field evidence remains valid; physical field matrix is still NOT_PROVEN."
      exit 0
    fi
    write_state "PAIR_RETRY_REQUIRED" "Previously passing pre-field evidence no longer passes; fail closed and re-pair."
    exit 13
    ;;

  INSTALL_PREPARATION_FAILED)
    write_state "NEW" "Retry requested after previous preparation failure."
    exec "$REPO/scripts/hakim-phone-field-run.sh" --restart-install
    ;;

  *)
    write_state "PAIR_RETRY_REQUIRED" "Unknown prior phase; fail closed without field promotion."
    exit 14
    ;;
esac
