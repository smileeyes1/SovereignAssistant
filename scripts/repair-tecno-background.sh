#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if ! command -v hakim-android >/dev/null 2>&1; then
  echo 'HAKIM command is unavailable; run the Android installer first.' >&2
  exit 2
fi

printf '\nHAKIM Ω — TECNO/HiOS background repair\n'
printf 'The last field test showed a long screen-off freeze. This helper opens the relevant controls, then reruns the same measured gate.\n\n'

# Standard Android battery exemption dialog. User consent is intentionally required.
am start -a android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS -d package:com.termux >/dev/null 2>&1 || \
  am start -a android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS >/dev/null 2>&1 || true
printf '١) في شاشة البطارية: اجعل Termux غير مقيّد / Unrestricted أو اسمح بتجاهل تحسين البطارية. ثم ارجع إلى Termux واضغط Enter.\n'
read -r

# App details catches HiOS variants that expose a second per-app power control.
am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.termux >/dev/null 2>&1 || true
printf '٢) داخل معلومات تطبيق Termux: افتح Battery/Power usage إن وجد، واختر Unrestricted/No restrictions، وتأكد أن Battery Saver ليس مفروضًا عليه. ثم ارجع واضغط Enter.\n'
read -r

# TECNO ships Phone Master/Battery Lab under these packages; open what exists.
opened_oem=false
for pkg in com.transsion.phonemaster com.transsion.batterylab com.transsion.phonemanager; do
  if monkey -p "$pkg" 1 >/dev/null 2>&1; then
    opened_oem=true
    break
  fi
done
printf '٣) في Phone Master / Battery Lab: فعّل Auto-start وBackground running لـ Termux، عطّل App Power Saving Management/Power Boost/Screen-off sleep لتطبيق Termux إن ظهرت. ثم ارجع واضغط Enter.\n'
if [ "$opened_oem" = false ]; then
  printf '   لم أستطع فتح تطبيق TECNO تلقائيًا؛ افتح Phone Master يدويًا وابحث عن Auto-start Management وBattery Lab.\n'
fi
read -r

printf '٤) افتح التطبيقات الحديثة وثبّت/اقفل بطاقة Termux بقفل 🔒 إن كان HiOS يوفر ذلك، ثم ارجع واضغط Enter.\n'
read -r

termux-wake-lock >/dev/null 2>&1 || true
RESULT="$(hakim-android background-test start --seconds 300 --interval 5)"
printf '%s\n' "$RESULT"
printf '\nالاختبار بدأ. اخرج من Termux من دون سحبه من التطبيقات الحديثة، أطفئ الشاشة ٥ دقائق كاملة، ثم افتح Termux. بعد نحو ٥:١٥ سنكون قادرين على قراءة النتيجة.\n'

(
  sleep 315
  status="$(hakim-android background-test status 2>/dev/null || printf '%s' '{"status":"ERROR"}')"
  printf '%s\n' "$status" > "$HOME/hakim-background-repair-result.json"
  final="$(printf '%s' "$status" | python -c 'import json,sys; print(json.load(sys.stdin).get("status","UNKNOWN"))' 2>/dev/null || echo UNKNOWN)"
  if command -v termux-notification >/dev/null 2>&1; then
    termux-notification --id 424243 --title 'HAKIM Ω — TECNO background repair' --content "النتيجة: $final" --priority high >/dev/null 2>&1 || true
  fi
) >/dev/null 2>&1 &
