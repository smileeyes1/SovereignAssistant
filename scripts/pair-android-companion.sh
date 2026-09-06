#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
mkdir -p "$HOME_DIR/.omega"
TOKEN_FILE="$HOME_DIR/.omega/companion.token"
if [ ! -s "$TOKEN_FILE" ]; then
  python - <<'PY' > "$TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(48))
PY
  chmod 600 "$TOKEN_FILE"
fi
TOKEN="$(cat "$TOKEN_FILE")"
termux-open-url "hakim://pair?token=$TOKEN"
printf '%s\n' 'HAKIM Companion pairing request opened locally.'
