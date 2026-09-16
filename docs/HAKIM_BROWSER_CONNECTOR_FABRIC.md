# نسيج موصل متصفح حكيم

## الغاية

هذه الطبقة تجعل متصفح حكيم المملوك قابلًا للاتصال من مساعد/موصل HTTPS مأذون دون فتح منفذ على الهاتف ودون shell عام. وهي طبقة تكييف فوق `HakimDirectRelay` الحالي؛ لا تستبدل حواجز الهاتف ولا توسع صلاحياته.

المسار:

`مساعد مأذون → HTTPS Connector → HC1 encrypted command → relay → HAKIM Companion → loopback browser control → HR1 encrypted result → Connector → assistant`

## حدود السلطة الثابتة

السطح المنشور: `status`, `ui`, `screenshot`, `action` فقط. `action` يقبل فقط أفعال متصفح حكيم المعروفة. لا `launch`، لا shell، لا أوامر ADB، لا device-wide action، ولا وصول للإشعارات عبر هذا الموصل. أفعال التغيير تبقى خاضعة لموافقة الهاتف المحلية التي يفرضها `HakimDirectRelay`.

## الأسرار

لا يُحفظ أي سر في GitHub. الخدمة تحتاج متغيرات بيئة خاصة في منصة النشر:

- `HAKIM_CONNECTOR_TOKEN`: رمز دخول مستقل للموصل، بطول ٣٢ محرفًا أو أكثر.
- `HAKIM_RELAY_KEY`: مفتاح relay نفسه الذي أُقرن به الهاتف، ويطابق عقد Android.
- `HAKIM_RELAY_TOPIC`: موضوع الأوامر الخاص.
- `HAKIM_RESULT_TOPIC`: موضوع النتائج الخاص والمختلف عن موضوع الأوامر.
- `HAKIM_RELAY_BASE`: افتراضيًا `https://ntfy.sh`، ولا يقبل إلا HTTPS.
- `HAKIM_REQUEST_TIMEOUT_MS`: اختياري؛ محصور بين ٣ و٦٠ ثانية.

يجب إدخال الأسرار من خزنة منصة النشر أو جلسة اقتران محلية مأذونة؛ لا تُنسخ إلى commit أو issue أو log.

## دلالة الصحة

`GET /api/connector` يثبت فقط أن خدمة الموصل مهيأة ومصادقتها تعمل. لا يثبت أن الهاتف متصل.

`POST /api/connector` مع `{"op":"status"}` لا ينجح إلا إذا أرسل الموصل HC1 واستقبل HR1 صالحًا يحمل request-id نفسه. عندها تكون `connector_round_trip=PROVEN`، لكن `field_verified` يبقى `false` لأن الجولة وحدها لا تعادل مصفوفة التأهيل الفيزيائي الكاملة.

النجاح الميداني الكامل يتطلب لاحقًا physical field gate على الهاتف الحقيقي + اختبار المتصفح الفعلي + دليل قابلية الاستخدام.

## الاستدامة والتعافي

١. المسار الأساسي: direct encrypted relay، مستقل عن Remote Desktop/ADB بعد الاقتران.
٢. المسار الاحتياطي: Remote Desktop Commander عندما يكون الجهاز متصلًا ومأذونًا، للتشخيص والإصلاح فقط.
٣. المسار المحلي: Termux/ADB recovery و`hakim-phone-field` عند الحاجة لإصلاح خدمة الجهاز أو تحديث النسخة.
٤. المراقبة السحابية: Automation/CI تعيد اكتشاف الواقع؛ لا تعتمد على ادعاء سابق أو ذاكرة جلسة.

فشل أي مسار لا يرفع حالة النجاح لمسار آخر. لا merge ولا FIELD promotion حتى تمر البوابات المطلوبة على نفس نسخة الكود المراد اعتمادها.

## OpenAPI

`connectors/hakim-browser-gateway/openapi.json` هو عقد قابل للاستيراد في أي موصل يدعم OpenAPI مع Bearer authentication. عنوان الخادم نسبي، لذلك يُربط تلقائيًا بعنوان النشر نفسه.
