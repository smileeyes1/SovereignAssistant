from pathlib import Path

BROKER = Path(__file__).resolve().parents[1] / "app" / "hakim" / "android_permission_broker.py"
RUNNER = Path(__file__).resolve().parents[1] / "app" / "hakim" / "run_android_sovereign.py"


def test_broker_does_not_depend_on_pm_package_query() -> None:
    text = BROKER.read_text(encoding="utf-8")
    assert "['pm', 'path', 'com.termux.api']" not in text
    assert 'notification backend failed; falling back to local browser gate' in text


def test_request_path_attempts_notification_then_local_fallback() -> None:
    text = BROKER.read_text(encoding="utf-8")
    assert 'self._notify(self._load(request_id), token)' in text
    assert 'self._start_browser_gate(self._load(request_id), token)' in text
    assert 'except Exception as exc:' in text


def test_doctor_does_not_claim_notification_pass_without_field_evidence() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "notification_gate" in text
    assert "NOT_PROVEN" in text
