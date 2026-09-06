#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="smileeyes1/SovereignAssistant"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
ROOT="$HOME_DIR/.omega/android-companion"
KEY_DIR="$HOME_DIR/.omega/keys"
mkdir -p "$ROOT" "$KEY_DIR"
chmod 700 "$ROOT" "$KEY_DIR"

pkg install -y apksigner openjdk-21 curl python >/dev/null

JSON="$ROOT/latest-release.json"
curl -fsSL --retry 4 --retry-delay 2 "https://api.github.com/repos/$REPO/releases/latest" -o "$JSON"

readarray -t URLS < <(python - "$JSON" <<'PY'
import json, sys
r=json.load(open(sys.argv[1], encoding='utf-8'))
assets={a['name']:a['browser_download_url'] for a in r.get('assets', [])}
for name in ('hakim-companion-unsigned.apk','hakim-companion-unsigned.apk.sha256'):
    if name not in assets: raise SystemExit(f'missing release asset: {name}')
    print(assets[name])
PY
)

UNSIGNED="$ROOT/hakim-companion-unsigned.apk"
SHA_FILE="$ROOT/hakim-companion-unsigned.apk.sha256"
SIGNED="$ROOT/hakim-companion-signed.apk"
curl -fsSL --retry 4 --retry-delay 2 "${URLS[0]}" -o "$UNSIGNED"
curl -fsSL --retry 4 --retry-delay 2 "${URLS[1]}" -o "$SHA_FILE"
(
  cd "$ROOT"
  sha256sum -c "$(basename "$SHA_FILE")"
)

KEYSTORE="$KEY_DIR/hakim-companion.jks"
PASSFILE="$KEY_DIR/hakim-companion.pass"
if [ ! -s "$PASSFILE" ]; then
  python - <<'PY' > "$PASSFILE"
import secrets
print(secrets.token_urlsafe(48))
PY
  chmod 600 "$PASSFILE"
fi
PASS="$(cat "$PASSFILE")"
if [ ! -s "$KEYSTORE" ]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass "$PASS" -keypass "$PASS" \
    -alias hakim-companion -keyalg RSA -keysize 4096 -validity 10000 \
    -dname "CN=HAKIM Omega Android Companion,O=HAKIM Omega" >/dev/null
  chmod 600 "$KEYSTORE"
fi

rm -f "$SIGNED"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias hakim-companion \
  --ks-pass "file:$PASSFILE" \
  --key-pass "file:$PASSFILE" \
  --out "$SIGNED" "$UNSIGNED"
apksigner verify --verbose --print-certs "$SIGNED" > "$ROOT/signature-verification.txt"
chmod 600 "$SIGNED" "$ROOT/signature-verification.txt"

python - "$SIGNED" "$ROOT/signature-verification.txt" <<'PY'
import hashlib, json, sys
apk, report=sys.argv[1:]
h=hashlib.sha256(open(apk,'rb').read()).hexdigest()
print(json.dumps({
  'status':'READY_FOR_USER_INSTALL',
  'signed_apk':apk,
  'sha256':h,
  'signature_verified':'Verifies' in open(report, encoding='utf-8', errors='replace').read(),
  'signing_key_location':'LOCAL_DEVICE_ONLY'
}, ensure_ascii=False, indent=2))
PY

termux-open --view --content-type application/vnd.android.package-archive "$SIGNED"
