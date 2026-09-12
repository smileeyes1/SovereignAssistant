#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="smileeyes1/SovereignAssistant"
PKG="org.hakim.omega.companion"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
ROOT="$HOME_DIR/.omega/android-companion"
KEY_DIR="$HOME_DIR/.omega/keys"
mkdir -p "$ROOT" "$KEY_DIR"
chmod 700 "$ROOT" "$KEY_DIR"

pkg install -y apksigner openjdk-21 curl python >/dev/null

JSON="$ROOT/latest-release.json"
curl -fsSL --retry 4 --retry-delay 2 "https://api.github.com/repos/$REPO/releases/latest" -o "$JSON"

readarray -t RELEASE < <(python - "$JSON" <<'PY'
import json, sys
r=json.load(open(sys.argv[1], encoding='utf-8'))
assets={a['name']:a for a in r.get('assets', [])}
required=('hakim-companion-unsigned.apk','hakim-companion-unsigned.apk.sha256','hakim-companion-build-manifest.json')
for name in required:
    if name not in assets:
        raise SystemExit(f'missing release asset: {name}')
print(assets['hakim-companion-unsigned.apk']['browser_download_url'])
print(assets['hakim-companion-unsigned.apk.sha256']['browser_download_url'])
print(assets['hakim-companion-build-manifest.json']['browser_download_url'])
print(r.get('target_commitish',''))
print((assets['hakim-companion-unsigned.apk'].get('digest') or '').removeprefix('sha256:'))
PY
)

[ "${#RELEASE[@]}" -eq 5 ] || { echo 'ERROR: incomplete release metadata' >&2; exit 2; }
APK_URL="${RELEASE[0]}"
SHA_URL="${RELEASE[1]}"
MANIFEST_URL="${RELEASE[2]}"
TARGET_COMMIT="${RELEASE[3]}"
RELEASE_DIGEST="${RELEASE[4]}"
[ -n "$TARGET_COMMIT" ] || { echo 'ERROR: release target commit is missing' >&2; exit 2; }

UNSIGNED="$ROOT/hakim-companion-unsigned.apk"
SHA_FILE="$ROOT/hakim-companion-unsigned.apk.sha256"
BUILD_MANIFEST="$ROOT/hakim-companion-build-manifest.json"
SOURCE_MANIFEST="$ROOT/AndroidManifest.source.xml"
SIGNED="$ROOT/hakim-companion-signed.apk"
VERIFY_REPORT="$ROOT/signature-verification.txt"
SIGNED_PROVENANCE="$ROOT/hakim-companion-signed-provenance.json"
CERT_PIN_FILE="$KEY_DIR/hakim-companion.cert.sha256"

curl -fsSL --retry 4 --retry-delay 2 "$APK_URL" -o "$UNSIGNED"
curl -fsSL --retry 4 --retry-delay 2 "$SHA_URL" -o "$SHA_FILE"
curl -fsSL --retry 4 --retry-delay 2 "$MANIFEST_URL" -o "$BUILD_MANIFEST"
(
  cd "$ROOT"
  sha256sum -c "$(basename "$SHA_FILE")"
)

UNSIGNED_SHA="$(sha256sum "$UNSIGNED" | awk '{print $1}')"
if [ -n "$RELEASE_DIGEST" ] && [ "$UNSIGNED_SHA" != "$RELEASE_DIGEST" ]; then
  echo 'ERROR: GitHub release digest does not match downloaded APK' >&2
  exit 3
fi

python - "$BUILD_MANIFEST" "$TARGET_COMMIT" "$UNSIGNED_SHA" <<'PY'
import json, sys
path, target, sha = sys.argv[1:]
m=json.load(open(path, encoding='utf-8'))
checks={
    'status': m.get('status') == 'UNSIGNED_SOURCE_BUILD_VERIFIED',
    'source_commit_sha': m.get('source_commit_sha') == target,
    'apk_sha256': m.get('apk_sha256') == sha,
    'signing_state': m.get('signing_state') == 'UNSIGNED',
    'required_final_signing': m.get('required_final_signing') == 'LOCAL_DEVICE_OWNED_KEY_ONLY',
}
failed=[k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('build manifest verification failed: ' + ','.join(failed))
print('BUILD_PROVENANCE=PROVEN')
PY

# Verify the exact source manifest at the immutable release commit. Signing cannot
# add Android services/permissions, so this binds the local signed APK to the safe core.
curl -fsSL --retry 4 --retry-delay 2 \
  "https://raw.githubusercontent.com/$REPO/$TARGET_COMMIT/android/hakim-companion/app/src/main/AndroidManifest.xml" \
  -o "$SOURCE_MANIFEST"
python - "$SOURCE_MANIFEST" <<'PY'
import sys
text=open(sys.argv[1], encoding='utf-8').read()
forbidden=(
    'HakimAccessibilityService',
    'HakimNotificationListener',
    'android.permission.BIND_ACCESSIBILITY_SERVICE',
    'android.service.notification.NotificationListenerService',
    'android.permission.SYSTEM_ALERT_WINDOW',
    'android.permission.REQUEST_INSTALL_PACKAGES',
    'android.permission.READ_SMS',
    'android.permission.READ_CONTACTS',
    'android.permission.READ_CALL_LOG',
    'android.permission.MANAGE_EXTERNAL_STORAGE',
)
present=[x for x in forbidden if x in text]
if present:
    raise SystemExit('unsafe Android manifest capability present: ' + ','.join(present))
required=(
    '<service android:name=".HakimForegroundService"',
    'android:exported="false"',
)
missing=[x for x in required if x not in text]
if missing:
    raise SystemExit('safe-core manifest invariant missing: ' + ','.join(missing))
print('SAFE_CORE_SOURCE_MANIFEST=PROVEN')
PY

KEYSTORE="$KEY_DIR/hakim-companion.jks"
PASSFILE="$KEY_DIR/hakim-companion.pass"

# Preserve signer continuity if a prior locally signed Hakim artifact exists.
PREVIOUS_SIGNER=""
if [ -s "$SIGNED" ]; then
  if apksigner verify --print-certs "$SIGNED" > "$ROOT/previous-signature-verification.txt" 2>/dev/null; then
    PREVIOUS_SIGNER="$(awk -F': ' '/certificate SHA-256 digest:/ {print tolower($2); exit}' "$ROOT/previous-signature-verification.txt" | tr -d '[:space:]')"
  fi
fi
rm -f "$ROOT/previous-signature-verification.txt"

PINNED_SIGNER=""
if [ -s "$CERT_PIN_FILE" ]; then
  PINNED_SIGNER="$(tr '[:upper:]' '[:lower:]' < "$CERT_PIN_FILE" | tr -d '[:space:]')"
fi

# If continuity evidence exists, never manufacture a replacement key silently.
if [ ! -s "$KEYSTORE" ] && { [ -n "$PREVIOUS_SIGNER" ] || [ -n "$PINNED_SIGNER" ]; }; then
  echo 'ERROR: previous Hakim signer exists but local keystore is missing; refusing silent key rotation' >&2
  exit 4
fi

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
cleanup_password_source() {
  rm -f "$KS_PASS_SOURCE"
}
trap cleanup_password_source EXIT INT TERM
chmod 600 "$KS_PASS_SOURCE"
printf '%s\n' "$PASS" > "$KS_PASS_SOURCE"

rm -f "$SIGNED" "$VERIFY_REPORT"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias hakim-companion \
  --ks-pass "file:$KS_PASS_SOURCE" \
  --out "$SIGNED" "$UNSIGNED"
apksigner verify --verbose --print-certs "$SIGNED" > "$VERIFY_REPORT"
chmod 600 "$SIGNED" "$VERIFY_REPORT"

NEW_SIGNER="$(awk -F': ' '/certificate SHA-256 digest:/ {print tolower($2); exit}' "$VERIFY_REPORT" | tr -d '[:space:]')"
[ -n "$NEW_SIGNER" ] || { echo 'ERROR: signer fingerprint missing after verification' >&2; exit 5; }
if [ -n "$PREVIOUS_SIGNER" ] && [ "$NEW_SIGNER" != "$PREVIOUS_SIGNER" ]; then
  echo 'ERROR: signer changed from previous locally signed Hakim APK' >&2
  exit 5
fi
if [ -n "$PINNED_SIGNER" ] && [ "$NEW_SIGNER" != "$PINNED_SIGNER" ]; then
  echo 'ERROR: signer does not match pinned Hakim certificate' >&2
  exit 5
fi
printf '%s\n' "$NEW_SIGNER" > "$CERT_PIN_FILE"
chmod 600 "$CERT_PIN_FILE"

SIGNED_SHA="$(sha256sum "$SIGNED" | awk '{print $1}')"
python - "$SIGNED_PROVENANCE" "$TARGET_COMMIT" "$UNSIGNED_SHA" "$SIGNED_SHA" "$NEW_SIGNER" <<'PY'
import json, sys
out, commit, unsigned_sha, signed_sha, signer = sys.argv[1:]
obj={
  'schema_version':'1.0',
  'status':'READY_FOR_USER_INSTALL',
  'source_commit_sha':commit,
  'unsigned_apk_sha256':unsigned_sha,
  'signed_apk_sha256':signed_sha,
  'signature_verified':True,
  'signer_sha256':signer,
  'signer_continuity':'PROVEN_OR_BASELINED_LOCALLY',
  'safe_core_source_manifest':'PROVEN',
  'signing_key_location':'LOCAL_DEVICE_ONLY',
  'physical_installation':'NOT_PROVEN_UNTIL_ANDROID_INSTALLS_THIS_APK',
}
open(out,'w',encoding='utf-8').write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(obj,ensure_ascii=False,indent=2))
PY
chmod 600 "$SIGNED_PROVENANCE"

PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"
PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"
PUBLIC_PROVENANCE="$PUBLIC_DOWNLOADS/HAKIM-Companion.provenance.json"
if [ -d "$PUBLIC_DOWNLOADS" ] && [ -w "$PUBLIC_DOWNLOADS" ]; then
  cp -f "$SIGNED" "$PUBLIC_APK"
  cp -f "$SIGNED_PROVENANCE" "$PUBLIC_PROVENANCE"
  PUBLIC_SHA="$(sha256sum "$PUBLIC_APK" | awk '{print $1}')"
  if [ "$PUBLIC_SHA" != "$SIGNED_SHA" ]; then
    echo 'ERROR: public Downloads APK hash mismatch' >&2
    rm -f "$PUBLIC_APK" "$PUBLIC_PROVENANCE"
    exit 6
  fi
  echo "INSTALL_FROM_PUBLIC_DOWNLOADS=$PUBLIC_APK"
  echo "SIGNED_SHA256=$SIGNED_SHA"
  echo "SIGNER_SHA256=$NEW_SIGNER"
  if command -v termux-open >/dev/null 2>&1; then
    termux-open --view "$PUBLIC_APK" >/dev/null 2>&1 || true
    echo 'INSTALLER_OPEN_REQUESTED=1'
  else
    echo "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk"
  fi
else
  echo "PUBLIC_DOWNLOADS_UNAVAILABLE=1"
  echo "Run termux-setup-storage once, allow storage access, then rerun this script." >&2
fi
