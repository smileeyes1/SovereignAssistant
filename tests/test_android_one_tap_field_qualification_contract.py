import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
GOV = ROOT / "governance"


def test_one_tap_local_qualification_is_wired_into_hakim_ui():
    main = (ANDROID / "MainActivity.kt").read_text(encoding="utf-8")
    assert 'button("تأهيل حكيم محليًا")' in main
    assert "runLocalQualification()" in main
    assert "LocalQualification.run(applicationContext)" in main
    assert "qualificationExecutor" in main


def test_local_qualification_proves_local_core_without_external_transport_or_field_overclaim():
    text = (ANDROID / "LocalQualification.kt").read_text(encoding="utf-8")
    for token in (
        '"SOVEREIGN_LOCAL"',
        '"field_verified", false',
        '"external_transport", false',
        "awaitLoopbackStatus",
        '"local_proof"',
        '"hakim-proof-input"',
        '"hakim-proof-button"',
        '"LOCAL_CORE_PASS"',
        '"PHYSICAL_PHONE_MATRIX_STILL_REQUIRED"',
    ):
        assert token in text
    assert "ntfy" not in text.lower()
    assert "make.com" not in text.lower()
    assert "TinyFish" not in text


def test_local_qualification_is_authenticated_and_does_not_persist_pair_secret():
    text = (ANDROID / "LocalQualification.kt").read_text(encoding="utf-8")
    assert 'setRequestProperty("Authorization", "Bearer $token")' in text
    assert '.putString(KEY_REPORT, report.toString())' in text
    report_body = text.split("private fun persist", 1)[0]
    assert '.put("pair_token"' not in report_body
    assert '.put("relay_key"' not in report_body


def test_status_exposes_only_sanitized_local_qualification_summary():
    server = (ANDROID / "LocalControlServer.kt").read_text(encoding="utf-8")
    local = (ANDROID / "LocalQualification.kt").read_text(encoding="utf-8")
    assert '.put("local_qualification", LocalQualification.summary(context))' in server
    summary_body = local.split("fun summary", 1)[1].split("private fun persist", 1)[0]
    assert '.put("field_verified", false)' in summary_body
    assert 'put("pair_token"' not in summary_body
    assert 'put("relay_key"' not in summary_body


def test_repository_field_claim_remains_fail_closed_until_real_physical_matrix_passes():
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
