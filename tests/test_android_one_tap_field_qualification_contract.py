import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion"
GOV = ROOT / "governance"


def test_one_tap_qualification_is_wired_into_hakim_ui():
    main = (ANDROID / "MainActivity.kt").read_text(encoding="utf-8")
    assert 'button("تأهيل حكيم")' in main
    assert "runFieldQualification()" in main
    assert "FieldQualification.run(applicationContext)" in main
    assert "qualificationExecutor" in main


def test_field_qualification_proves_core_round_trip_without_overclaiming_field_status():
    text = (ANDROID / "FieldQualification.kt").read_text(encoding="utf-8")
    for token in (
        'CARRIER_PREFIX = "HC1."',
        'RESULT_PREFIX = "HR1."',
        'CARRIER_AAD = "HAKIM-CARRIER-v1"',
        'RESULT_AAD = "HAKIM-RESULT-v1"',
        "encryptedStatusRoundTrip",
        '"CORE_REMOTE_ROUND_TRIP_PASS"',
        '.put("field_verified", false)',
        '"SCREEN_OFF_REBOOT_FINANCIAL_COMPATIBILITY"',
    ):
        assert token in text


def test_self_test_is_adversarial_and_financial_mode_is_not_auto_disabled():
    text = (ANDROID / "FieldQualification.kt").read_text(encoding="utf-8")
    for token in (
        '"rejects_bad_hmac"',
        '"rejects_plaintext_carrier"',
        '"rejects_bad_gcm_tag"',
        "127.0.0.1",
        "FinancialSafeMode.isEnabled",
    ):
        assert token in text
    assert "FinancialSafeMode.enter(" not in text
    assert "FinancialSafeMode.exit(" not in text


def test_qualification_report_does_not_persist_pair_or_relay_secrets():
    text = (ANDROID / "FieldQualification.kt").read_text(encoding="utf-8")
    assert '.putString(KEY_REPORT, report.toString())' in text
    assert '.putString("pair_token"' not in text
    assert f'.putString(HakimDirectRelay.KEY_RELAY_KEY' not in text
    assert 'report.put("relay_key"' not in text
    assert 'report.put("pair_token"' not in text


def test_status_exposes_only_sanitized_qualification_summary_for_remote_closed_loop():
    server = (ANDROID / "LocalControlServer.kt").read_text(encoding="utf-8")
    assert 'qualificationSummary(prefs)' in server
    assert '.put("field_qualification", qualificationSummary(prefs))' in server
    assert '.put("field_verified", false)' in server
    assert '.put("encrypted_status_round_trip", roundTrip)' in server
    assert '.put("next_gate", report.optString("next_gate", "UNKNOWN"))' in server
    # لا يُعاد التقرير الخام ولا أسرار الاقتران/القناة في ملخص الحالة البعيد.
    summary_body = server.split("private fun qualificationSummary", 1)[1].split("private fun route", 1)[0]
    assert 'put("pair_token"' not in summary_body
    assert 'put("relay_key"' not in summary_body
    assert 'put("relay_topic"' not in summary_body


def test_repository_field_claim_remains_fail_closed_until_real_physical_matrix_passes():
    state = json.loads((GOV / "HAKIM_ACTIVE_STATE.json").read_text(encoding="utf-8"))
    assert state["field_phone"]["field_verified"] is False
    assert state["promotion_evidence"]["physical_phone_round_trip"] == "NOT_PROVEN"
    assert state["financial_safety"]["physical_financial_app_compatibility"] == "NOT_PROVEN"
    required = set(state["required_physical_matrix"])
    assert {"SCREEN_OFF_BACKGROUND", "REBOOT_CONTINUITY", "TARGET_FINANCIAL_APPS_COMPATIBILITY_IN_SAFE_MODE"} <= required
