from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_android_ci_executes_notification_safe_core_runtime_gate():
    workflow = text(".github/workflows/android-companion.yml")
    assert "scripts/android-companion-emulator-notification-gate.sh" in workflow
    assert "sh scripts/android-companion-emulator-runtime-gate.sh && sh scripts/android-companion-emulator-notification-gate.sh" in workflow


def test_notification_gate_proves_authority_absent_and_endpoint_fail_closed():
    gate = text("scripts/android-companion-emulator-notification-gate.sh")
    assert "set -eu" in gate
    assert '"notification_access":false' in gate
    assert "HakimNotificationListener" in gate
    assert "unexpectedly registered in safe core" in gate
    assert '"error":"disabled_in_safe_core"' in gate
    assert '"reason":"notification_access_not_registered"' in gate
    assert "[ \"$code\" = '410' ]" in gate
    assert "cmd notification allow_listener" not in gate
    assert "cmd notification disallow_listener" not in gate
    assert "EMULATOR_NOTIFICATION_LISTENER=NOT_REGISTERED_SAFE_CORE" in gate
    assert "PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_APPLICABLE_SAFE_CORE" in gate
