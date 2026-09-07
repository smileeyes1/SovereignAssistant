from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_android_ci_executes_notification_listener_runtime_gate():
    workflow = text(".github/workflows/android-companion.yml")
    assert "scripts/android-companion-emulator-notification-gate.sh" in workflow
    assert "sh scripts/android-companion-emulator-runtime-gate.sh && sh scripts/android-companion-emulator-notification-gate.sh" in workflow


def test_notification_gate_proves_grant_event_revocation_without_physical_claim():
    gate = text("scripts/android-companion-emulator-notification-gate.sh")
    assert "set -eu" in gate
    assert 'cmd notification allow_listener "$LISTENER"' in gate
    assert '"notification_listener":true' in gate
    assert "cmd notification post -S bigtext" in gate
    assert "HAKIM_EMULATOR_NOTIFICATION_PROBE" in gate
    assert "notification-listener-event-observed" in gate
    assert '"package":"com.android.shell"' in gate
    assert 'cmd notification disallow_listener "$LISTENER"' in gate
    assert '"notification_listener":false' in gate
    assert "notification_listener_unavailable" in gate
    assert "[ \"$code\" = '409' ]" in gate
    assert "EMULATOR_NOTIFICATION_LISTENER=PROVEN" in gate
    assert "PHYSICAL_TECNO_NOTIFICATION_FIELD_QUALIFICATION=NOT_PROVEN" in gate
