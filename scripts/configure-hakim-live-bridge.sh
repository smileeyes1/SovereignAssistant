#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TOPIC="${1:-${HAKIM_RELAY_TOPIC:-}}"
RESULT_URL="${2:-${HAKIM_RESULT_URL:-}}"
RELAY_KEY="${3:-${HAKIM_RELAY_KEY:-}}"

if [[ ! "$TOPIC" =~ ^[A-Za-z0-9_-]{20,120}$ ]]; then
  echo 'ERROR: relay topic is missing or invalid' >&2
  exit 2
fi
if [[ ! "$RESULT_URL" =~ ^https:// ]]; then
  echo 'ERROR: HTTPS result URL is missing or invalid' >&2
  exit 2
fi
if [[ ! "$RELAY_KEY" =~ ^[A-Za-z0-9_-]{40,100}$ ]]; then
  echo 'ERROR: relay signing key is missing or invalid' >&2
  exit 2
fi

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

PAIR_URI="$(TOKEN="$TOKEN" TOPIC="$TOPIC" RESULT_URL="$RESULT_URL" RELAY_KEY="$RELAY_KEY" python - <<'PY'
import os, urllib.parse
q=urllib.parse.urlencode({
    'token': os.environ['TOKEN'],
    'relay_topic': os.environ['TOPIC'],
    'result_url': os.environ['RESULT_URL'],
    'relay_key': os.environ['RELAY_KEY'],
})
print('hakim://pair?' + q)
PY
)"

termux-open-url "$PAIR_URI"
printf '%s\n' 'HAKIM signed live bridge pairing/configuration request opened locally.'
printf '%s\n' 'Android remains the authority for Accessibility, notifications, and consequential-action approvals.'
