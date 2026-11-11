# عقد نسيج متصفح حكيم ذاتي التعافي

الحالة: SOURCE CONTRACT — ليس تحققًا ميدانيًا.

الهدف: جعل متصفح حكيم عقدة تنفيذ ذاتية التعافي مستقلة عن Remote Desktop وADB، دون فتح shell عام أو توسيع صلاحيات Android.

## الثوابت
- خط الأساس عند إنشاء الفرع: `8901db4efcaa998b209dca8293a9dc9e5306e4e7`.
- لا تغيير package أو signer أو versionCode في هذا العمل.
- `result_topic` هو عقد النتيجة القانوني؛ `result_url` legacy ممنوع.
- SOURCE/CI/SIGNED/FIELD حالات مستقلة؛ لا FIELD_PASS بلا دليل مباشر من الجهاز.

## غلاف المهمة
كل مهمة يجب أن تحمل على الأقل: `request_id`, `issued_at`, `expires_at`, `nonce`, `command`, `payload`, ووسيلة تحقق من الأصالة. الأسرار لا تدخل المستودع ولا سجل الأدلة.

## التنفيذ
المسموح أوامر متصفح محددة في allowlist فقط. لا أوامر نظام عامة، لا remote shell، ولا تجاوز حماية المنصة. كل أمر يمر: RECEIVED → VALIDATED → RUNNING → SUCCEEDED|FAILED → ACKED.

## الاستمرارية
يُحفظ inbox/outbox وحالة المهمة محليًا بطريقة ذرية. عند فقد الشبكة أو موت العملية، تُستعاد الحالة ولا يعاد الأثر المؤثر مرتين. إعادة الاتصال تستخدم exponential backoff مع jitter وحد أعلى، بلا busy-loop.

## الأمان
رفض مغلق عند: انتهاء الصلاحية، فشل المصادقة، nonce/request_id مكرر، payload أكبر من الحد، command غير مسموح، أو بيانات تالفة. يجب توفير kill switch محلي وحدود معدل وحجم.

## الخصوصية والأدلة
الدليل الأدنى: request_id أو hash مناسب، الحالة، timestamps، error class، وعدّاد المحاولات. لا يُحفظ payload/result الخام ولا token/key/secret.

## اختبارات القبول في CI
- duplicate وreplay.
- expired وinvalid-auth.
- oversize وunsupported-command.
- network-loss ثم reconnect.
- process-death ثم restore.
- result retry وack loss وout-of-order.
- idempotency guard للأفعال المؤثرة.
- regression يثبت `result_topic` ويمنع `result_url`.
- privacy regression يمنع raw payload/result/secrets من evidence.
- manifest/permission regression يثبت عدم إضافة صلاحيات Android.

## بوابة الدمج
لا يدمج التنفيذ قبل نجاح الاختبارات ذات الصلة وعدم وجود توسيع صلاحيات أو أسرار. أي تغيير يحتاج صلاحية جديدة أو وصولًا صحيًا/حسابيًا يخرج إلى تفويض مستقل. الاختبار الميداني مرحلة لاحقة منفصلة.