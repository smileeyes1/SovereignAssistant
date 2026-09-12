#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cat >&2 <<'EOF'
هذا المسار القديم أُلغي عمدًا لأنه كان يهيئ ناقلًا خارجيًا.
المسار الحاكم الآن هو حكيم السيادي المحلي:
  ١) bash scripts/install-android-companion-local.sh
  ٢) ثبّت HAKIM-Companion.apk من التنزيلات.
  ٣) bash scripts/pair-android-companion.sh
لا خيارات مطور، لا تصحيح لاسلكي، لا Accessibility، لا Notification Listener، ولا ناقل خلفي خارجي في التشغيل العادي.
EOF
exit 64
