from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_airplane_gate_is_pre_field_and_preserves_invariants():
    gate = text("scripts/android-companion-emulator-airplane-gate.sh")
    assert "cmd connectivity airplane-mode enable" in gate
    assert "settings get global airplane_mode_on" in gate
    assert '"loopback_only":true' in gate
    assert '"control_server_listening":true' in gate
    assert '"persistent_model_allowed":false' in gate
    assert "llama-server" in gate
    assert "EMULATOR_AIRPLANE_LOCAL_CONTROL=PROVEN" in gate
    assert "EMULATOR_AIRPLANE_PROCESS_RECOVERY=PROVEN" in gate
    assert "PHYSICAL_TECNO_OFFLINE_FIELD_QUALIFICATION=NOT_PROVEN" in gate
    assert "cmd connectivity airplane-mode disable" in gate


def test_workflow_runs_airplane_gate_in_existing_android15_emulator():
    workflow = text(".github/workflows/android-companion.yml")
    assert "scripts/android-companion-emulator-airplane-gate.sh" in workflow
    assert "tests/test_android_airplane_emulator_gate_contract.py" in workflow
