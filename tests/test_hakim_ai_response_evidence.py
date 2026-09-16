from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimAiResponseEvidence.kt"


def text():
    return EVIDENCE.read_text(encoding="utf-8")


def test_response_evidence_is_privacy_minimal_and_allowlisted():
    s = text()
    assert "HakimAiGovernance.isSupportedUrl(pageUrl)" in s
    assert 'putString("last_response_hash", hash)' in s
    assert 'putInt("last_response_length", body.length)' in s
    assert 'putString("last_response_host", host)' in s
    assert 'putLong("observed_responses"' in s
    assert "لا يُحفظ نص الرد" in s
    assert 'putString("last_response_text"' not in s


def test_response_evidence_deduplicates_and_bounds_input():
    s = text()
    assert "body.isBlank() || body.length > 500_000" in s
    assert 'getString("last_response_hash", null) == hash' in s
    assert 'MessageDigest.getInstance("SHA-256")' in s
