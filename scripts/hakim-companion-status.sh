#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
T="$HOME/.omega/companion.token"
[ -s "$T" ] || { echo '{"status":"NOT_PAIRED"}'; exit 2; }
curl -fsS --max-time 3 -H "Authorization: Bearer $(cat "$T")" http://127.0.0.1:47651/v1/status
