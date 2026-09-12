#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="smileeyes1/SovereignAssistant"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
ROOT="$HOME_DIR/.omega/android-companion"
KEY_DIR="$HOME_DIR/.omega/keys"
mkdir -p "$ROOT" "$KEY_DIR"
chmod 700 "$ROOT" "$KEY_DIR"

pkg install -y apksigner aapt openjdk-21 curl python >/dev/null
for tool in apksigner zipalign aapt keytool; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: missing required tool: $tool" >&2; exit 2; }
done

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
ALIGNED="$ROOT/hakim-companion-aligned.apk"
SHA_FILE="$ROOT/hakim-companion-unsigned.apk.sha256"
SIGNED="$ROOT/hakim-companion-signed.apk"
curl -fsSL --retry 4 --retry-delay 2 "${URLS[0]}" -o "$UNSIGNED"
curl -fsSL --retry 4 --retry-delay 2 "${URLS[1]}" -o "$SHA_FILE"
(
  cd "$ROOT"
  sha256sum -c "$(basename "$SHA_FILE")"
)

aapt dump badging "$UNSIGNED" > "$ROOT/unsigned-badging.txt"
grep -F "package: name='org.hakim.omega.companion'" "$ROOT/unsigned-badging.txt" >/dev/null || {
  echo 'ERROR: downloaded APK package identity is invalid' >&2; exit 3;
}

rm -f "$ALIGNED" "$SIGNED"
zipalign -f 4 "$UNSIGNED" "$ALIGNED"
zipalign -c -v 4 "$ALIGNED" > "$ROOT/zipalign-verification.txt"

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

KS_PASS_SOURCE="$(mktemp "$ROOT/.ks-pass.XXXXXX")"
cleanup_password_source() { rm -f "$KS_PASS_SOURCE"; }
trap cleanup_password_source EXIT INT TERM
chmod 600 "$KS_PASS_SOURCE"
printf '%s\n' "$PASS" > "$KS_PASS_SOURCE"

apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias hakim-companion \
  --ks-pass "file:$KS_PASS_SOURCE" \
  --v1-signing-enabled false \
  --v2-signing-enabled true \
  --v3-signing-enabled true \
  --out "$SIGNED" "$ALIGNED"

apksigner verify --verbose --print-certs "$SIGNED" > "$ROOT/signature-verification.txt"
aapt dump badging "$SIGNED" > "$ROOT/signed-badging.txt"
grep -F "package: name='org.hakim.omega.companion'" "$ROOT/signed-badging.txt" >/dev/null || {
  echo 'ERROR: signed APK failed package parsing preflight' >&2; exit 5;
}
chmod 600 "$SIGNED" "$ROOT/signature-verification.txt" "$ROOT/signed-badging.txt" "$ROOT/zipalign-verification.txt"

python - "$SIGNED" "$ROOT/signature-verification.txt" <<'PY'
import hashlib, json, sys
apk, report=sys.argv[1:]
text=open(report, encoding='utf-8', errors='replace').read()
h=hashlib.sha256(open(apk,'rb').read()).hexdigest()
print(json.dumps({
  'status':'READY_FOR_USER_INSTALL',
  'signed_apk':apk,
  'sha256':h,
  'signature_verified':'Verifies' in text,
  'zipalign_verified':True,
  'android_package_parse_preflight':True,
  'signing_key_location':'LOCAL_DEVICE_ONLY'
}, ensure_ascii=False, indent=2))
PY

PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"
PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"
if [ -d "$PUBLIC_DOWNLOADS" ] && [ -w "$PUBLIC_DOWNLOADS" ]; then
  cp -f "$SIGNED" "$PUBLIC_APK"
  PUBLIC_SHA="$(sha256sum "$PUBLIC_APK" | awk '{print $1}')"
  SIGNED_SHA="$(sha256sum "$SIGNED" | awk '{print $1}')"
  if [ "$PUBLIC_SHA" != "$SIGNED_SHA" ]; then
    echo 'ERROR: public Downloads APK hash mismatch' >&2
    rm -f "$PUBLIC_APK"
    exit 6
  fi
  echo "INSTALL_FROM_PUBLIC_DOWNLOADS=$PUBLIC_APK"
  echo "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk"
  if command -v termux-open >/dev/null 2>&1; then
    termux-open --view --content-type application/vnd.android.package-archive "$PUBLIC_APK" >/dev/null 2>&1 || true
  fi
else
  echo "PUBLIC_DOWNLOADS_UNAVAILABLE=1"
  echo "Run termux-setup-storage once, allow storage access, then rerun this script." >&2
fi
