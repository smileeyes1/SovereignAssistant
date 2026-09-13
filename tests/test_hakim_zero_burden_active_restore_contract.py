from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / 'governance' / 'HAKIM_ACTIVE.json'
REGISTRY = ROOT / 'governance' / 'ACTIVE_ADDITIVE_RULES_v1.txt'
RULE = ROOT / 'governance' / 'HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md'


def test_zero_burden_rule_is_in_active_restore_path():
    d = json.loads(ACTIVE.read_text(encoding='utf-8'))
    assert d['additive_rules_registry'] == 'governance/ACTIVE_ADDITIVE_RULES_v1.txt'
    assert d['zero_burden_self_sovereign_rule'] == 'governance/HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md'
    seq = d['restore_sequence']
    assert 'LOAD_ACTIVE_ADDITIVE_RULES' in seq
    assert 'LOAD_ZERO_BURDEN_SELF_SOVEREIGN_RULE' in seq
    assert seq.index('LOAD_ACTIVE_ADDITIVE_RULES') < seq.index('LOAD_VALUE_GATES_SPEC')
    assert seq.index('LOAD_ZERO_BURDEN_SELF_SOVEREIGN_RULE') < seq.index('LOAD_VALUE_GATES_SPEC')
    assert 'ZERO_BURDEN_SELF_SOVEREIGN_RULE_CONTRACT_PASS' in d['promotion_gate']


def test_registry_points_to_zero_burden_rule():
    s = REGISTRY.read_text(encoding='utf-8')
    assert 'HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md' in s


def test_rule_prevents_regression_to_repeated_manual_work():
    s = RULE.read_text(encoding='utf-8')
    for token in [
        'لا تُعِد المستخدم إلى سلسلة أوامر أو اختبارات سبق نجاحها',
        'self-heal تلقائيًا',
        'كل سطح مرجعي قابل للكتابة وملائم للاستعادة',
        'منع نشر الأسرار أو مفاتيح التوقيع أو بيانات الاعتماد',
        'سجل القواعد المضافة النشطة قبل التخطيط الخاص بالمهمة',
    ]:
        assert token in s
