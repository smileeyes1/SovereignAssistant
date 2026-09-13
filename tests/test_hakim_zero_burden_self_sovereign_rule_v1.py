from pathlib import Path

RULE = Path('governance/HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md')


def text():
    return RULE.read_text(encoding='utf-8')


def test_rule_exists_and_has_core_contract():
    s = text()
    for token in [
        'لا تُرجع للمستخدم خطوة يستطيع حكيم تنفيذها',
        'FREE_CORE',
        'LAST_VERIFIED_BASELINE',
        'PROVEN_SUCCESS',
        'ROLLBACK',
        'FIELD_VERIFIED',
    ]:
        assert token in s


def test_all_things_does_not_expand_authority():
    s = text()
    assert '«كل شيء» لا يعني تجاوز' in s
    assert 'الصلاحيات' in s


def test_manual_burden_is_minimized_not_faked():
    s = text()
    assert 'الافتراضي هو صفر خطوات يدوية إضافية' in s
    assert 'إجراءً محليًا لا يمكن تنفيذه عن بعد' in s
    assert 'أقل تدخل ممكن' in s


def test_tool_failure_has_fallback_behavior():
    s = text()
    assert 'إذا فشلت وسيلة' in s
    assert 'شخّص الجذر' in s
    assert 'بديل مشروع وآمن ومتاح' in s
    assert 'لا توقف الغاية' in s


def test_success_requires_evidence():
    s = text()
    assert 'نجاح الأداة أو جزء من السلسلة لا يُعد نجاحًا للناتج' in s
    assert 'لا تستخدم COMPLETE/FIELD_VERIFIED إلا بدليل خاص' in s
