from pathlib import Path

from app.hakim.android_permission_broker import AndroidPermissionBroker
from app.hakim.run_android_sovereign import _approval_security_self_test


def test_wrong_token_self_test_preserves_pending_state(tmp_path: Path) -> None:
    broker = AndroidPermissionBroker(tmp_path)
    result = _approval_security_self_test(broker)
    assert result['status'] == 'PASS'
    assert result['wrong_token_rejected'] is True
    assert result['state_before'] == 'pending'
    assert result['state_after_wrong_token'] == 'pending'
    assert result['cleanup_final_status'] == 'rejected'
    assert result['token_exposed'] is False

    audit = (tmp_path / '.omega' / 'approvals' / 'audit.jsonl').read_text(encoding='utf-8')
    assert 'approval.invalid_token' in audit
    assert 'HAKIM-intentionally-wrong-token' not in audit
