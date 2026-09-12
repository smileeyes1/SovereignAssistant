from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt"


def source():
    return SERVER.read_text(encoding="utf-8")


def test_all_mutating_actions_require_request_identity_and_durable_claim():
    s = source()
    assert 'headers["x-hakim-request-id"]' in s
    assert 'action != "home"' not in s
    assert 'request_id_required' in s
    assert 'duplicate_request' in s
    assert 'getSharedPreferences("hakim_idempotency", Context.MODE_PRIVATE)' in s
    assert 'prefs.contains(requestId)' in s
    assert 'putLong(requestId, System.currentTimeMillis()).commit()' in s
    assert '@Synchronized' in s


def test_missing_owned_browser_fails_closed_before_idempotency_claim():
    s = source()
    browser_check = s.index('else if (!HakimBrowserController.isAttached())')
    claim_check = s.index('else if (!claimRequest(requestId))')
    assert browser_check < claim_check
    assert 'browser_unavailable' in s


def test_action_response_always_returns_non_null_request_identity():
    s = source()
    assert 'put("request_id", requestId)' in s
    assert 'requestId ?: JSONObject.NULL' not in s
