#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TOPIC="${1:-${HAKIM_RELAY_TOPIC:-}}"
RESULT_URL="${2:-${HAKIM_RESULT_URL:-}}"
ROOT="${OMEGA_ROOT:-$HOME/hakim-workspace}"

if [[ ! "$TOPIC" =~ ^[A-Za-z0-9_-]{20,120}$ ]]; then
  echo 'ERROR: relay topic is missing or invalid' >&2
  exit 2
fi
if [[ ! "$RESULT_URL" =~ ^https:// ]]; then
  echo 'ERROR: HTTPS result URL is missing or invalid' >&2
  exit 2
fi
if [ ! -d "$ROOT/.git" ]; then
  echo "ERROR: HAKIM workspace not found at $ROOT" >&2
  exit 3
fi

cd "$ROOT"
git pull --ff-only

bash scripts/install-android-companion-local.sh

printf '\n%s\n' 'بعد ظهور مُثبّت أندرويد: ثبّت تطبيق حكيم، ثم ارجع إلى Termux واضغط Enter فقط.'
read -r _

bash scripts/configure-hakim-live-bridge.sh "$TOPIC" "$RESULT_URL"

printf '\n%s\n' 'افتح تطبيق حكيم وفعّل فقط ما يطلبه أندرويد للتحكم بالواجهة والوصول إلى الإشعارات.'
printf '%s\n' 'بعد ذلك تبقى أوامر تغيير حالة الهاتف خلف موافقة محلية صريحة.'
