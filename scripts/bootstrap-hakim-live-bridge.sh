#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cat >&2 <<'EOF'
تم إيقاف bootstrap الخاص بالجسر الخارجي القديم عمدًا.
المسار الحاكم الآن هو حكيم السيادي المحلي: تطبيق واحد، خادم محلي loopback، متصفح حكيم المملوك، ومهام موقعة يفتحها المستخدم صراحة.
لا تُنشئ قناة خلفية أو ناقلًا خارجيًا تلقائيًا.
للاقتران المحلي فقط استخدم: scripts/pair-android-companion.sh
EOF
exit 64
