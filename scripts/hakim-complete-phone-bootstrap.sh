#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"
INSTALLER="$ROOT/scripts/install-android-companion-local.sh"
PAIR_TOKEN_FILE="$OMEGA/hakim-companion-pair-token"
SIGNED_APK="$OMEGA/android-companion/hakim-companion-signed.apk"
PKG="org.hakim.omega.companion"
LOCAL_PORT=48765

[ -f "$CFG" ] || { echo 'ERROR: missing HAKIM ADB config; complete the one-time Android wireless-debug pairing first.' >&2; exit 2; }
[ -x "$INSTALLER" ] || [ -f "$INSTALLER" ] || { echo 'ERROR: installer script missing; git pull the HAKIM repository first.' >&2; exit 3; }

readarray -t CFG_VALUES < <(python - "$CFG" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8'))
for k in ('adb_target','topic','result_url','relay_key'):
    print(str(x.get(k,'')))
PY
)
TARGET="${CFG_VALUES[0]}"
TOPIC="${CFG_VALUES[1]}"
RESULT_URL="${CFG_VALUES[2]}"
RELAY_KEY="${CFG_VALUES[3]}"

[ -n "$TARGET" ] || { echo 'ERROR: adb_target missing; run hakim-adb-pair first.' >&2; exit 4; }
[ -n "$TOPIC" ] && [ -n "$RESULT_URL" ] && [ -n "$RELAY_KEY" ] || { echo 'ERROR: private relay config incomplete.' >&2; exit 5; }
adb -s "$TARGET" get-state 2>/dev/null | grep -qx device || { echo 'ERROR: paired Android device is not reachable over ADB.' >&2; exit 6; }

echo '① تنزيل أحدث إصدار موثوق وتوقيعه بمفتاح الهاتف المحلي...'
bash "$INSTALLER"
[ -s "$SIGNED_APK" ] || { echo 'ERROR: signed APK not produced.' >&2; exit 7; }
apksigner verify --verbose "$SIGNED_APK" >/dev/null

echo '② تثبيت HAKIM Companion عبر جسر الصيانة ADB...'
INSTALL_OUT="$OMEGA/hakim-adb-install.out"
if ! adb -s "$TARGET" install -r "$SIGNED_APK" >"$INSTALL_OUT" 2>&1; then
    cat "$INSTALL_OUT" >&2
    echo 'ERROR: Android/Play Protect rejected the maintenance install. No protection was bypassed.' >&2
    exit 8
fi
cat "$INSTALL_OUT"

if [ ! -s "$PAIR_TOKEN_FILE" ]; then
    python - <<'PY' > "$PAIR_TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(48))
PY
    chmod 600 "$PAIR_TOKEN_FILE"
fi
PAIR_TOKEN="$(cat "$PAIR_TOKEN_FILE")"
[ ${#PAIR_TOKEN} -ge 32 ] || { echo 'ERROR: local pair token invalid.' >&2; exit 9; }

PAIR_URI="$(python - "$PAIR_TOKEN" "$TOPIC" "$RESULT_URL" "$RELAY_KEY" <<'PY'
import sys
from urllib.parse import urlencode
print('hakim://pair?' + urlencode({
    'token':sys.argv[1],
    'relay_topic':sys.argv[2],
    'result_url':sys.argv[3],
    'relay_key':sys.argv[4],
}))
PY
)"

echo '③ تهيئة الاقتران المحلي والقناة البعيدة الخاصة...'
adb -s "$TARGET" shell am force-stop "$PKG" >/dev/null 2>&1 || true
adb -s "$TARGET" shell am start -W -n "$PKG/.MainActivity" -a android.intent.action.VIEW -d "$PAIR_URI" >/dev/null
sleep 2

adb -s "$TARGET" forward --remove "tcp:$LOCAL_PORT" >/dev/null 2>&1 || true
adb -s "$TARGET" forward "tcp:$LOCAL_PORT" tcp:47651 >/dev/null
STATUS_FILE="$OMEGA/hakim-companion-bootstrap-status.json"
READY=0
for _ in $(seq 1 20); do
    if curl -fsS --max-time 3 -H "Authorization: Bearer $PAIR_TOKEN" "http://127.0.0.1:$LOCAL_PORT/v1/status" -o "$STATUS_FILE"; then
        READY=1
        break
    fi
    sleep 1
 done

if [ "$READY" -ne 1 ]; then
    echo 'ERROR: Companion installed but its loopback control server did not become reachable.' >&2
    exit 10
fi
python -m json.tool "$STATUS_FILE" 2>/dev/null || cat "$STATUS_FILE"

echo '④ فتح معالج حكيم المحلي لأقل الموافقات التي يفرضها أندرويد...'
adb -s "$TARGET" shell am start -W -n "$PKG/.MainActivity" >/dev/null

ACCESS="$(python - "$STATUS_FILE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); print('1' if x.get('accessibility') else '0')
PY
)"
NOTIFY="$(python - "$STATUS_FILE" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); print('1' if x.get('notification_listener') else '0')
PY
)"
if [ "$ACCESS" != 1 ]; then
    adb -s "$TARGET" shell am start -a android.settings.ACCESSIBILITY_SETTINGS >/dev/null 2>&1 || true
fi

cat <<'EOF'
✅ HAKIM_COMPANION_BOOTSTRAP_PREPARED
- التطبيق مثبت وموقّع بمفتاح محفوظ على الهاتف فقط.
- الاقتران المحلي والقناة الخاصة مهيآن.
- الخادم المحلي loopback اجتاز فحص الوصول.
- لا يوجد remote shell عام ولا تعطيل لـ Play Protect.

أندرويد وحده يفرض الموافقات المحلية الحساسة (Accessibility/Notification access). بعد إكمالها يعود حكيم للتطبيق عبر زر «أفضل خطوة قادمة» ويصبح جاهزًا لاختبارات الجولة الحية.
EOF

if [ "$ACCESS" = 1 ] && [ "$NOTIFY" = 1 ]; then
    echo '✅ LOCAL_APPROVALS_ALREADY_READY'
else
    echo '⏳ LOCAL_ANDROID_APPROVALS_PENDING'
fi
