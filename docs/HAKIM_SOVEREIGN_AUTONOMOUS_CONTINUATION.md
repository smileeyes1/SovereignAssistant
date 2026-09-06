# Ω HAKIM — SOVEREIGN AUTONOMOUS CONTINUATION PROFILE

> This is a **domain/project profile** subordinate to `docs/OMEGA_SOVEREIGN_OPERATING_CONSTITUTION.md`. It adds HAKIM/Android/repository constraints and may not weaken or override the universal constitution. The terms «الركن» and «الفرض» are engineering/runtime classifications, not religious rulings.

## Canonical load order

`Ω SOVEREIGN OPERATING CONSTITUTION → HAKIM PROFILE → CURRENT STATE CAPSULE → EXECUTION`

The mutable HAKIM recovery state lives in `docs/HAKIM_STATE_CAPSULE.md`; this Profile must not embed mutable SHA values, current CI results, release IDs, or temporary blockers.

## 1. HAKIM mission

استأنف `smileeyes1/SovereignAssistant` من آخر حالة صحيحة مثبتة بالأدلة الفعلية الآن. الغاية الخاصة بهذا الملف: HAKIM محلي سيادي، مستقل قدر الإمكان، منخفض العبء، قادر على القيادة والتنفيذ والتحقق والتعافي على الهاتف، مع إبقاء المستخدم مستخدمًا نهائيًا لا مطورًا.

## 2. Protected HAKIM baselines

احمِ كـGolden Baselines:

- `Local Sovereign Mode`
- `Android Permission Gate`
- `LOW_RESOURCE_ANDROID`
- `HAKIM Android Companion`
- كل نجاح ميداني مثبت في Issue #42 أو evidence ledger المعتمد

## 3. Repository/CI profile

أي تغيير في المستودع يتبع Branch/PR واختبارات مناسبة. لا تدمج إلا بعد نجاح البوابات المطلوبة ومطابقة `tested head SHA` مع رأس PR. بعد الدمج أعد التحقق على `main` نفسه.

يجب أن يبقى:

`python -m pip install .`

ناجحًا. مجلد `android/` ليس Python package. حافظ على `Verify Python package installability` كـRegression Gate دائم، مع Governance + Reality + أي Gate متعلق بالتغيير.

## 4. LOW_RESOURCE_ANDROID profile

الهدف الميداني:

`TECNO POVA 7 / Android 15 / SDK 35 / arm64 / 7.5 GiB RAM`

ممنوع جعل نموذج محلي مقيمًا أو `local-LLM autonomous planning` جزءًا من runtime الحاكم. النواة حتمية وخفيفة. النموذج المحلي **عند الطلب فقط** بموارد محافظة ثم يُغلق فورًا. الاستقرار والحرارة والبطارية والـRAM تتقدم على حجم النموذج أو قدرته النظرية.

## 5. Device-control profile

`Remote Desktop Commander` جسر صيانة اختياري، وليس runtime dependency.

Android Companion يجب أن يحافظ على:

- `loopback-only` authenticated control plane
- device-owned / `LOCAL_DEVICE_ONLY` signing key
- عدم رفع signing key أو password إلى GitHub
- Human Gate للصلاحيات الجديدة والأفعال السيادية

عند توفر قناة الجهاز:

1. حدّث الهاتف إلى آخر `main` مثبت.
2. تحقق من عدم وجود `llama-server` مقيم.
3. شغّل `scripts/install-android-companion-local.sh`.
4. أكمل الاقتران والتأهيل.

بعد التثبيت اختبر ميدانيًا وبالأدلة:

- authentication
- loopback isolation
- status
- Accessibility
- UI tree
- screenshot
- navigation / tap / swipe / text
- Notification Listener
- foreground/background
- reboot/boot continuity
- offline/airplane behavior
- crash/restart/recovery
- backup/restore
- no persistent model

سجل الأدلة في Issue #42.

أضف Shizuku/ADB فقط إذا أثبت اختبار ميداني فجوة ضرورية لا يحققها Companion الحالي. لا تستخدم root أو Device Owner إلا بعد ثبوت الضرورة وموافقة سيادية صريحة.

## 6. HAKIM automation topology

الترتيب المفضل:

1. GitHub event-driven automation فورًا.
2. GitHub deadman/watchdog دوري لمنع الفشل الصامت.
3. ChatGPT supervisory/recovery automation كطبقة خارجية مستقلة.
4. HAKIM المحلي الخفيف كطبقة التشغيل النهائية على الجهاز.

تعطل أي طبقة صيانة أو إشراف لا يجب أن يوقف النواة المحلية ما لم تكن هناك تبعية حقيقية مثبتة.

## 7. Mutable state separation

كل SHA أو PASS/FAIL آني أو release/tag أو device-online state أو blocker مؤقت ينتمي إلى `docs/HAKIM_STATE_CAPSULE.md`، لا إلى هذا الـProfile. عند كل تشغيل تُقرأ الكبسولة كـ`RECOVERY HINT` فقط ثم يعاد التحقق من GitHub/CI/الجهاز قبل اعتماد أي قيمة منها.
