#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
MINUTES="${1:-60}"
if ! [[ "$MINUTES" =~ ^[0-9]{1,4}$ ]]; then echo 'ERROR: minutes must be a number' >&2; exit 2; fi
if [ "$MINUTES" -lt 0 ] || [ "$MINUTES" -gt 1440 ]; then echo 'ERROR: allowed range is 0..1440 minutes' >&2; exit 2; fi
FILE="$HOME/.omega/hakim-control-until"
mkdir -p "$HOME/.omega"
chmod 700 "$HOME/.omega"
if [ "$MINUTES" -eq 0 ]; then
  printf '0\n' > "$FILE"
  chmod 600 "$FILE"
  echo '🔒 تم إغلاق نافذة التحكم المحلي.'
  exit 0
fi
UNTIL="$(( $(date +%s) * 1000 + MINUTES * 60 * 1000 ))"
printf '%s\n' "$UNTIL" > "$FILE"
chmod 600 "$FILE"
echo "🔓 نافذة التحكم المحلي مفعّلة لمدة $MINUTES دقيقة."
