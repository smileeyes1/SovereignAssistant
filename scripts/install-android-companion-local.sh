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

readarray -t RELEASE_META < <(python - "$JSON" <<'PY'
import json, sys
r=json.load(open(sys.argv[1], encoding='utf-8'))
assets={a['name']:a['browser_download_url'] for a in r.get('assets', [])}
required=(
    'hakim-companion-unsigned.apk',
    'hakim-companion-unsigned.apk.sha256',
    'hakim-companion-build-manifest.json',
)
for name in required:
    if name not in assets:
        raise SystemExit(f'missing release asset: {name}')
print(r.get('target_commitish',''))
for name in required:
    print(assets[name])
PY
)

TARGET_COMMIT="${RELEASE_META[0]}"
UNSIGNED="$ROOT/hakim-companion-unsigned.apk"
SHA_FILE="$ROOT/hakim-companion-unsigned.apk.sha256"
MANIFEST="$ROOT/hakim-companion-build-manifest.json"
SIGNED="$ROOT/hakim-companion-signed.apk"
VERIFIED_RELEASE="$ROOT/verified-release.json"

curl -fsSL --retry 4 --retry-delay 2 "${RELEASE_META[1]}" -o "$UNSIGNED"
curl -fsSL --retry 4 --retry-delay 2 "${RELEASE_META[2]}" -o "$SHA_FILE"
curl -fsSL --retry 4 --retry-delay 2 "${RELEASE_META[3]}" -o "$MANIFEST"
(
  cd "$ROOT"
  sha256sum -c "$(basename "$SHA_FILE")"
)

TARGET_COMMIT="$TARGET_COMMIT" python - "$UNSIGNED" "$SHA_FILE" "$MANIFEST" "$VERIFIED_RELEASE" <<'PY'
import hashlib, json, os, sys
from pathlib import Path

apk, sha_file, manifest_file, out_file = map(Path, sys.argv[1:])
target = os.environ.get('TARGET_COMMIT','')
manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
actual = hashlib.sha256(apk.read_bytes()).hexdigest()
recorded = sha_file.read_text(encoding='utf-8').split()[0].strip()
source = str(manifest.get('source_commit_sha',''))
manifest_sha = str(manifest.get('apk_sha256',''))
android_tree = str(manifest.get('android_tree_sha',''))

checks = {
    'source_commit_matches_release': source == target and len(source) == 40,
    'apk_sha_matches_sha_file': actual == recorded,
    'apk_sha_matches_manifest': actual == manifest_sha and len(manifest_sha) == 64,
    'android_tree_recorded': len(android_tree) == 40,
    'artifact_name_matches': manifest.get('artifact') == 'hakim-companion-unsigned.apk',
    'signing_state_unsigned': manifest.get('signing_state') == 'UNSIGNED',
    'build_does_not_claim_field_verification': manifest.get('field_verification') == 'NOT_PROVEN_BY_BUILD',
}
if not all(checks.values()):
    raise SystemExit('release provenance verification failed: ' + json.dumps(checks, ensure_ascii=False))

payload = {
    'status': 'SOURCE_RELEASE_VERIFIED',
    'source_commit_sha': source,
    'android_tree_sha': android_tree,
    'unsigned_apk_sha256': actual,
    'field_verification': 'NOT_PROVEN',
    'checks': checks,
}
out = Path(out_file)
tmp = out.with_name('.' + out.name + '.tmp')
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
tmp.chmod(0o600)
tmp.replace(out)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

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

python - "$SIGNED" "$ROOT/signature-verification.txt" "$VERIFIED_RELEASE" <<'PY'
import hashlib, json, sys
from pathlib import Path
apk, report, verified = map(Path, sys.argv[1:])
h=hashlib.sha256(apk.read_bytes()).hexdigest()
source=json.loads(verified.read_text(encoding='utf-8'))
print(json.dumps({
  'status':'READY_FOR_USER_INSTALL',
  'signed_apk':str(apk),
  'sha256':h,
  'signature_verified':'Verifies' in report.read_text(encoding='utf-8', errors='replace'),
  'signing_key_location':'LOCAL_DEVICE_ONLY',
  'source_release_status':source.get('status'),
  'source_commit_sha':source.get('source_commit_sha'),
  'android_tree_sha':source.get('android_tree_sha'),
  'field_verification':'NOT_PROVEN',
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
  if command -v termux-open >/dev/null 2>&1; then
    if termux-open --view "$PUBLIC_APK" >/dev/null 2>&1; then
      echo 'ANDROID_PACKAGE_INSTALLER_OPENED=1'
      echo 'USER_ACTION_REQUIRED=approve Android package installation if prompted'
    else
      echo 'ANDROID_PACKAGE_INSTALLER_OPEN_FAILED=1'
      echo "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk"
    fi
  else
    echo "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk"
  fi
else
  echo "PUBLIC_DOWNLOADS_UNAVAILABLE=1" >&2
  echo "Run termux-setup-storage once, allow storage access, then rerun this script." >&2
  exit 6
fi
