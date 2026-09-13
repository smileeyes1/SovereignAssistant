from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / 'governance' / 'HAKIM_ACTIVE.json'
REGISTRY = ROOT / 'governance' / 'ACTIVE_ADDITIVE_RULES_v1.txt'
RULE = ROOT / 'governance' / 'HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md'

EXPECTED_RESTORE = [
    'LOAD_ACTIVE_POINTER', 'LOAD_CANONICAL', 'LOAD_NSTAR_SPEC',
    'LOAD_NSTAR_GOVERNING_CONSTITUTION', 'LOAD_INTELLIGENCE_FABRIC_SPEC',
    'LOAD_INTELLIGENCE_MATRIX', 'LOAD_META_METHOD_SPEC', 'LOAD_MAX_VALUE_INTENT_RULE',
    'LOAD_VALUE_GATES_SPEC', 'LOAD_CONTINUITY_SHIELD_SPEC', 'LOAD_CONTINUITY_SHIELD_POLICY',
    'LOAD_CAPABILITY_TRANSITIONS', 'LOAD_PHONE_SOVEREIGN_CONSTRAINTS',
    'LOAD_RUNTIME_POLICY', 'LOAD_BRIDGE_POLICY', 'LOAD_ACTIVE_STATE',
    'LOAD_BRIDGE_HEALTH', 'VERIFY_FRESHNESS', 'RESUME_FROM_LAST_PROVEN_POINT',
]


def test_frozen_active_contract_is_not_mutated_by_additive_rule():
    d = json.loads(ACTIVE.read_text(encoding='utf-8'))
    assert d['version'] == '2.3'
    assert d['restore_sequence'] == EXPECTED_RESTORE
    assert 'additive_rules_registry' not in d
    assert 'zero_burden_self_sovereign_rule' not in d


def test_registry_points_to_zero_burden_rule_and_orders_it_before_task_planning():
    s = REGISTRY.read_text(encoding='utf-8')
    assert 'HAKIM_ZERO_BURDEN_SELF_SOVEREIGN_RULE_v1.md' in s
    assert 'Load after the existing canonical baseline and before task-specific planning.' in s
    assert 'does not replace a frozen baseline' in s


def test_rule_prevents_regression_to_repeated_manual_work():
    s = RULE.read_text(encoding='utf-8')
    for token in [
        'لا تُعِد المستخدم إلى سلسلة أوامر أو اختبارات سبق نجاحها',
        'self-heal تلقائيًا',
        'كل سطح مرجعي قابل للكتابة وملائم للاستعادة',
        'منع نشر الأسرار أو مفاتيح التوقيع أو بيانات الاعتماد',
        'سجل القواعد المضافة النشطة قبل التخطيط الخاص بالمهمة',
        'LAST_VERIFIED_BASELINE',
        'PROVEN_SUCCESS',
        'ROLLBACK',
    ]:
        assert token in s
