from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_android_ci_executes_notification_privacy_runtime_gate():
    workflow = text(".github/workflows/android-companion.yml")
    assert "scripts/android-companion-emulator-notification-gate.sh" in workflow
    assert "sh scripts/android-companion-emulator-runtime-gate.sh && sh scripts/android-companion-emulator-notification-gate.sh" in workflow


def test_notification_gate_proves_listener_absence_and_content_nondisclosure_without_physical_claim():
    gate = text("scripts/android-companion-emulator-notification-gate.sh")
    assert "set -eu" in gate
    assert '"notification_listener":false' in gate
    assert "notification_listener_disabled_by_play_protect_safe_mode" in gate
    assert "cmd notification post -S bigtext" in gate
    assert "must-not-be-readable-by-hakim" in gate
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" in gate
    assert "allow_listener" not in gate
    assert "disallow_listener" not in gate
    assert "EMULATOR_NOTIFICATION_LISTENER_ABSENT=PROVEN" in gate
    assert "EMULATOR_NOTIFICATION_PRIVACY_FAIL_CLOSED=PROVEN" in gate
    assert "PHYSICAL_PHONE_NOTIFICATION_PRIVACY_FIELD_QUALIFICATION=NOT_PROVEN" in gate
