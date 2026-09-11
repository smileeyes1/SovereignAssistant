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
if [ -z "$PASS" ]; then
  echo 'ERROR: Android signing password file is empty' >&2
  exit 4
fi
if [ ! -s "$KEYSTORE" ]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass "$PASS" -keypass "$PASS" \
    -alias hakim-companion -keyalg RSA -keysize 4096 -validity 10000 \
    -dname "CN=HAKIM Omega Android Companion,O=HAKIM Omega" >/dev/null
  chmod 600 "$KEYSTORE"
fi

# The key is created with the same password as the keystore. apksigner reuses
# the keystore password for the key when --key-pass is omitted, so there is no
# second password-file read that can reach EOF.
KS_PASS_SOURCE="$(mktemp "$ROOT/.ks-pass.XXXXXX")"
cleanup_password_source() {
  rm -f "$KS_PASS_SOURCE"
}
trap cleanup_password_source EXIT INT TERM
chmod 600 "$KS_PASS_SOURCE"
printf '%s\n' "$PASS" > "$KS_PASS_SOURCE"

rm -f "$SIGNED"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias hakim-companion \
  --ks-pass "file:$KS_PASS_SOURCE" \
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

# Some Android/Termux combinations can fail to let Package Installer read a
# content URI backed by Termux private storage even when the APK is valid.
# Prefer a public Downloads handoff when storage access has already been granted.
PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"
PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"
if [ -d "$PUBLIC_DOWNLOADS" ] && [ -w "$PUBLIC_DOWNLOADS" ]; then
  cp -f "$SIGNED" "$PUBLIC_APK"
  PUBLIC_SHA="$(sha256sum "$PUBLIC_APK" | awk '{print $1}')"
  SIGNED_SHA="$(sha256sum "$SIGNED" | awk '{print $1}')"
  if [ "$PUBLIC_SHA" != "$SIGNED_SHA" ]; then
    echo 'ERROR: public Downloads APK hash mismatch' >&2
    rm -f "$PUBLIC_APK"
    exit 5
  fi
  echo "INSTALL_FROM_PUBLIC_DOWNLOADS=$PUBLIC_APK"
  echo "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk"
else
  echo "PUBLIC_DOWNLOADS_UNAVAILABLE=1"
  echo "Run termux-setup-storage once, allow storage access, then rerun this script." >&2
fi
