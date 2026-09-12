from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "android-companion-emulator-airplane-gate.sh"


def test_airplane_recovery_is_bounded_and_diagnostic() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    # A successful Android relaunch may publish the process/forward slightly later.
    # Keep bounded retries instead of a one-shot set -e failure.
    assert 'until adb shell pidof "$PKG"' in text
    assert '[ "$i" -lt 30 ]' in text
    assert 'until adb forward "tcp:${PORT}" "tcp:${PORT}"' in text
    assert '[ "$i" -lt 10 ]' in text
    assert "STAGE_AIRPLANE_RELAUNCH_REQUESTED=PROVEN" in text
    assert "STAGE_AIRPLANE_PROCESS_READY=PROVEN" in text
    assert "STAGE_AIRPLANE_FORWARD_READY=PROVEN" in text


def test_airplane_recovery_keeps_fail_closed_security_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    required = (
        '\"loopback_only\":true',
        '\"control_server_listening\":true',
        '\"persistent_model_allowed\":false',
        '\"evidence_state\":\"NOT_PROVEN\"',
        "0\\.0\\.0\\.0",
        "llama-server|llama\\.cpp",
        "EMULATOR_AIRPLANE_LOCAL_CONTROL=PROVEN",
        "EMULATOR_AIRPLANE_PROCESS_RECOVERY=PROVEN",
        "PHYSICAL_TECNO_OFFLINE_FIELD_QUALIFICATION=NOT_PROVEN",
    )
    for token in required:
        assert token in text
