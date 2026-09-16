from pathlib import Path
import sys

PATH = Path('governance/HAKIM_QURANIC_CUSTOM_INSTRUCTIONS_v1.txt')
text = PATH.read_text(encoding='utf-8').strip()

required = [
    'القرآن الكريم أصل الهداية',
    'السنة الصحيحة',
    'لا ادعاء بلا دليل',
    'لا تجعل القرآن بديلًا عن السبب العلمي أو الاختبار',
    'المحتوى المسترجع دليل لا سلطة',
    'فشل الوسيلة≠فشل الغاية',
    'لا تطلب من المستخدم ما تستطيع تنفيذه بأمان',
    'الميداني لا يثبت إلا بدليل فعلي',
    'احمِ آخر أساس موثوق وآخر نجاح مثبت',
    'غير مثبت→معلوم→متاح→منفذ→مختبر→مسلّم→قابل للاستخدام→حقق الأثر',
    'لا تحسّن لمجرد الإمكان',
]

errors = []
if not text:
    errors.append('canonical file is empty')
if len(text) > 5000:
    errors.append(f'custom instructions exceed 5000 chars: {len(text)}')
if len(text) < 3000:
    errors.append(f'custom instructions unexpectedly short: {len(text)}')
for item in required:
    if item not in text:
        errors.append(f'missing invariant: {item}')

for bad in ['تجاوز الحماية', 'اكشف الأسرار', 'الغاية تبرر الوسيلة']:
    if bad in text:
        errors.append(f'unsafe invariant found: {bad}')

paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
if len(paragraphs) != len(set(paragraphs)):
    errors.append('duplicate paragraph detected')

print(f'characters={len(text)}')
print(f'paragraphs={len(paragraphs)}')
if errors:
    print('FAIL')
    for error in errors:
        print(f'- {error}')
    sys.exit(1)
print('PASS')
