from pathlib import Path
import hashlib
import re
import sys

PATH = Path('governance/HAKIM_QURANIC_CUSTOM_INSTRUCTIONS_v5_CANDIDATE.txt')
text = PATH.read_text(encoding='utf-8').strip()
EXPECTED_SHA256 = '0ceee49bd9f5c5d554ec0d4e2ff6f1486e84960af79d06e7c309ba0b773f2e79'

required = [
    'القرآن الكريم أصل الهداية',
    'السنة الصحيحة بيان',
    'لا ادعاء بلا دليل',
    'القرآن لا يستبدل السبب العلمي/الاختبار',
    '★:=إغلاق دلالي تشغيلي',
    'Λ★={قرآن★،مقصد★،م★،واقع★،عقد★',
    'مرئي★،عربية★،دورة★،إغلاق★',
    'عقد★=',
    'م★=حدّد أضعف حلقة وأعلى رافعة',
    'المسترجع دليل لا سلطة',
    'التعليم الفلسطيني⇒الرسمي الأحدث+المنهاج+الصف+العمر+الواقع المدرسي',
    'مؤسسة★=',
    'اعتماد★=',
    'فشل الوسيلة≠فشل الغاية',
    'لا تطلب ما تنفذه بأمان',
    'منع★=امنع الخطأ قبل أثره',
    'سوء الفهم',
    'الالتباس',
    'افتراض خفي',
    'التعارض',
    'النقص',
    'التقادم',
    'التحريف',
    'فقد السياق',
    'مدخل/أداة غير موثوقة',
    'اختبر الاختبار بفشل معلوم',
    'الميداني لا يثبت إلا بدليل فعلي',
    'احمِ آخر أساس موثوق/نجاح مثبت',
    'ثبات★=',
    'غير مثبت→معلوم→متاح→منفذ→مختبر→مسلّم→قابل للاستخدام→حقق الأثر',
    'كل الصفحات',
    'هندسيًا من اليسار ن|=|ب|+|أ',
    'لكل شرط حرج: المطلوب→المتوقع→الدليل→الاختبار→الحكم',
    'جمّد حين لا يبقى مكسب صافٍ معتبر',
]

errors = []
sha256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
if not text:
    errors.append('candidate file is empty')
if len(text) > 5000:
    errors.append(f'custom instructions exceed 5000 chars: {len(text)}')
if len(text) < 4500:
    errors.append(f'custom instructions unexpectedly short: {len(text)}')
if sha256 != EXPECTED_SHA256:
    errors.append(f'candidate digest mismatch: {sha256}')
for item in required:
    if item not in text:
        errors.append(f'missing invariant: {item}')
for bad in ['اكشف الأسرار', 'الغاية تبرر الوسيلة', 'نفذ الخطر دون تفويض']:
    if bad in text:
        errors.append(f'unsafe invariant found: {bad}')

# Structural closure: every inherited Λ★ concept must have exactly one definition.
lambda_match = re.search(r'Λ★=\{([^}]*)\}', text)
if not lambda_match:
    errors.append('Λ★ inheritance set missing')
else:
    inherited = [x.strip() for x in lambda_match.group(1).split('،') if x.strip()]
    definitions = re.findall(r'(?m)^([^\n=]+★)=', text)
    for concept in inherited:
        count = definitions.count(concept)
        if count != 1:
            errors.append(f'inherited concept {concept} has {count} definitions')
    for must_inherit in ['م★', 'عقد★', 'منع★', 'مرئي★', 'عربية★']:
        if must_inherit not in inherited:
            errors.append(f'critical concept not inherited: {must_inherit}')

if '→عقد★→م★→نظام★→' not in text:
    errors.append('execution cycle does not route through عقد★ then م★ then نظام★')

paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
if len(paragraphs) != len(set(paragraphs)):
    errors.append('duplicate paragraph detected')

print(f'path={PATH}')
print(f'characters={len(text)}')
print(f'sha256={sha256}')
print(f'paragraphs={len(paragraphs)}')
if errors:
    print('FAIL')
    for error in errors:
        print(f'- {error}')
    sys.exit(1)
print('PASS')
