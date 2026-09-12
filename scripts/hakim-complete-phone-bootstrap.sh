#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${OMEGA_ROOT:-$HOME/.omega/hakim-live-src}"
OMEGA="$HOME/.omega"
CFG="$OMEGA/hakim-termux-adb.json"
INSTALLER="$ROOT/scripts/install-android-companion-local.sh"
CLOSE_MAINT="$ROOT/scripts/hakim-close-adb-maintenance.sh"
PAIR_TOKEN_FILE="$OMEGA/hakim-companion-pair-token"
SIGNED_APK="$OMEGA/android-companion/hakim-companion-signed.apk"
STATUS_FILE="$OMEGA/hakim-companion-bootstrap-status.json"
PKG="org.hakim.omega.companion"
LOCAL_PORT=48765
APPROVAL_TIMEOUT_SECONDS="${HAKIM_APPROVAL_TIMEOUT_SECONDS:-600}"

[ -f "$CFG" ] || { echo 'ERROR: missing HAKIM ADB config; complete the conditional one-time Android wireless-debug pairing first.' >&2; exit 2; }
[ -f "$INSTALLER" ] || { echo 'ERROR: installer script missing; git pull the HAKIM repository first.' >&2; exit 3; }
[ -f "$CLOSE_MAINT" ] || { echo 'ERROR: maintenance-close script missing.' >&2; exit 3; }

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

echo '② تثبيت HAKIM Companion عبر جسر الصيانة المؤقت...'
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

refresh_forward() {
  adb -s "$TARGET" forward --remove "tcp:$LOCAL_PORT" >/dev/null 2>&1 || true
  adb -s "$TARGET" forward "tcp:$LOCAL_PORT" tcp:47651 >/dev/null
}
fetch_status() {
  curl -fsS --max-time 3 -H "Authorization: Bearer $PAIR_TOKEN" "http://127.0.0.1:$LOCAL_PORT/v1/status" -o "$STATUS_FILE"
}
status_flag() {
  python - "$STATUS_FILE" "$1" <<'PY'
import json,sys
try: x=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: raise SystemExit(2)
print('1' if x.get(sys.argv[2]) else '0')
PY
}

refresh_forward
READY=0
for _ in $(seq 1 30); do
    if fetch_status; then READY=1; break; fi
    sleep 1
done
[ "$READY" -eq 1 ] || { echo 'ERROR: Companion installed but loopback control server did not become reachable.' >&2; exit 10; }
python -m json.tool "$STATUS_FILE" 2>/dev/null || cat "$STATUS_FILE"

echo '④ معالج الموافقات المحلية: أندرويد سيعرض فقط ما لا يستطيع أي وكيل اعتماده بدلًا منك.'
adb -s "$TARGET" shell am start -W -n "$PKG/.MainActivity" >/dev/null 2>&1 || true
sleep 2

ACCESS="$(status_flag accessibility)"
NOTIFY="$(status_flag notification_listener)"
if [ "$ACCESS" != 1 ]; then
    echo '➡️ فعّل «حكيم» في شاشة إمكانية الوصول؛ لا حاجة للعودة إلى Termux.'
    adb -s "$TARGET" shell am start -a android.settings.ACCESSIBILITY_SETTINGS >/dev/null 2>&1 || true
fi

DEADLINE=$(( $(date +%s) + APPROVAL_TIMEOUT_SECONDS ))
NOTIFY_SCREEN_OPENED=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if ! adb -s "$TARGET" get-state 2>/dev/null | grep -qx device; then
        echo 'ERROR: maintenance ADB disappeared before local approvals completed; state preserved for resume.' >&2
        exit 11
    fi
    refresh_forward
    if fetch_status; then
        ACCESS="$(status_flag accessibility)"
        NOTIFY="$(status_flag notification_listener)"
        if [ "$ACCESS" = 1 ] && [ "$NOTIFY" != 1 ] && [ "$NOTIFY_SCREEN_OPENED" = 0 ]; then
            echo '✅ إمكانية الوصول مفعّلة. أفتح الآن شاشة الوصول إلى الإشعارات تلقائيًا...'
            adb -s "$TARGET" shell am start -a android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS >/dev/null 2>&1 || \
            adb -s "$TARGET" shell am start -a android.settings.NOTIFICATION_LISTENER_SETTINGS >/dev/null 2>&1 || \
            adb -s "$TARGET" shell am start -a android.settings.NOTIFICATION_LISTENER_DETAIL_SETTINGS >/dev/null 2>&1 || true
            NOTIFY_SCREEN_OPENED=1
        fi
        if [ "$ACCESS" = 1 ] && [ "$NOTIFY" = 1 ]; then
            echo '✅ LOCAL_ANDROID_APPROVALS_READY'
            break
        fi
    fi
    sleep 2
done

if [ "$ACCESS" != 1 ] || [ "$NOTIFY" != 1 ]; then
    echo '⏳ LOCAL_ANDROID_APPROVALS_PENDING — انتهت مهلة الانتظار دون تجاوز موافقة أندرويد. الحالة محفوظة ويمكن إعادة تشغيل نفس الأمر.'
    exit 12
fi

# One last local readiness check immediately before retiring the maintenance bridge.
refresh_forward
fetch_status
python -m json.tool "$STATUS_FILE" 2>/dev/null || cat "$STATUS_FILE"

echo '⑤ الموافقات جاهزة. أطلب الآن إغلاق ADB/خيارات المطور؛ إثبات الاستقلال النهائي سيكون بجولة Companion بعيدة لاحقة.'
bash "$CLOSE_MAINT"

cat <<'EOF'
✅ HAKIM_COMPANION_BOOTSTRAP_LOCAL_PHASE_COMPLETE
- Companion مثبت وموقع محليًا ومهيأ للقناة الخاصة.
- loopback والموافقات المحلية اجتازت فحص الجاهزية.
- جسر ADB لم يعد اعتمادًا للتشغيل المعتاد، وطُلب إغلاقه بعد تحقق Developer Options=0.
- المرحلة التالية آلية من الخارج: signed round-trip عبر Companion وحده ثم مصفوفة FIELD كاملة.
EOF
