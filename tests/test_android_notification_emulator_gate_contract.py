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
    assert "Notification listener component is not registered" in gate
    assert '"error":"notification_access_unavailable"' in gate
    assert "[ \"$code\" = '409' ]" in gate
    assert "cmd notification allow_listener" not in gate
    assert "cmd notification disallow_listener" not in gate
    assert "EMULATOR_NOTIFICATION_LISTENER=REGISTERED_DISABLED_BY_DEFAULT" in gate
    assert "PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_PROVEN" in gate
