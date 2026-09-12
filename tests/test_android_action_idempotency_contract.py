from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/LocalControlServer.kt"


def source():
    return SERVER.read_text(encoding="utf-8")


def test_browser_actions_require_request_identity_and_durable_claim():
    s = source()
    assert 'headers["x-hakim-request-id"]' in s
    assert 'request_id_required' in s
    assert 'duplicate_request' in s
    assert 'getSharedPreferences("hakim_idempotency", Context.MODE_PRIVATE)' in s
    assert 'prefs.contains(requestId)' in s
    assert 'putLong(requestId, System.currentTimeMillis()).commit()' in s
    assert '@Synchronized' in s


def test_missing_owned_browser_fails_closed():
    s = source()
    assert '!HakimBrowserController.isAttached()' in s
    assert 'browser_unavailable' in s
    assert 'HakimBrowserController.action(JSONObject(body))' in s


def test_device_wide_home_exception_is_not_present_in_safe_core():
    s = source()
    assert 'action != "home"' not in s
    assert 'HakimAccessibilityService' not in s
