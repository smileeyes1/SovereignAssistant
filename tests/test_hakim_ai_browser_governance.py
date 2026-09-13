from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimAiGovernance.kt"
BROWSER = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/HakimBrowserController.kt"
MAIN = ROOT / "android/hakim-companion/app/src/main/java/org/hakim/omega/companion/MainActivity.kt"
GRADLE = ROOT / "android/hakim-companion/app/build.gradle.kts"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_governance_is_local_and_does_not_claim_system_override():
    s = text(ENGINE)
    assert "لا تدّعي أنها تغيّر system/developer instructions" in s
    assert "تعليمات المنصة والسلامة والحقوق الأعلى" in s
    assert 'MARKER = "[[HAKIM::GOVERNED::v1]]"' in s


def test_supported_ai_hosts_are_explicit_allowlist():
    s = text(ENGINE)
    for host in ["chatgpt.com", "gemini.google.com", "claude.ai", "copilot.microsoft.com", "perplexity.ai"]:
        assert f'"{host}"' in s
    assert "return host in supportedHosts" in s


def test_full_kernel_exceeds_custom_instruction_limit_and_turn_kernel_is_separate():
    s = text(ENGINE)
    full = s.split('private const val FULL_KERNEL = """', 1)[1].split('"""', 1)[0]
    turn = s.split('private const val TURN_KERNEL = """', 1)[1].split('"""', 1)[0]
    assert len(full) > 5000
    assert len(turn) < len(full)
    assert "لا تنتظر أمر «تابع»" in full


def test_browser_intercepts_send_before_submission_and_only_on_supported_pages():
    s = text(BROWSER)
    assert 'addJavascriptInterface(GovernanceBridge' in s
    assert 'HakimNative.isSupported' in s
    assert "document.addEventListener('keydown'" in s
    assert "document.addEventListener('click'" in s
    assert "HakimNative.prepare" in s
    assert "startsWith(marker)" in s


def test_chatgpt_is_default_governed_entry_and_version_bumped():
    m = text(MAIN)
    g = text(GRADLE)
    assert 'button("ChatGPT عبر حكيم")' in m
    assert "HakimBrowserController.installGovernanceHooks()" in m
    assert "HakimBrowserController.openChatGpt()" in m
    assert "versionCode = 20019" in g
    assert 'versionName = "0.6.0-governed-ai-browser"' in g
