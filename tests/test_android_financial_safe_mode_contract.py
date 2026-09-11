from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app" / "src" / "main"
JAVA = APP / "java" / "org" / "hakim" / "omega" / "companion"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_financial_safe_mode_is_persistent_and_fail_closed():
    t = read(JAVA / "FinancialSafeMode.kt")
    assert 'const val KEY = "financial_safe_mode"' in t
    assert ".putBoolean(KEY, true)" in t
    assert "disableSelf()" in t
    assert "requestUnbind()" in t
    assert "stopService(Intent(context, HakimForegroundService::class.java))" in t


def test_financial_safe_mode_blocks_restart_paths():
    main = read(JAVA / "MainActivity.kt")
    boot = read(JAVA / "BootReceiver.kt")
    service = read(JAVA / "HakimForegroundService.kt")
    assert main.count("!FinancialSafeMode.isEnabled(this)") >= 3
    assert "if (FinancialSafeMode.isEnabled(context)) return" in boot
    assert "if (FinancialSafeMode.isEnabled(context)) return" in service
    assert "START_NOT_STICKY" in service


def test_normal_companion_control_does_not_require_developer_options_or_adb():
    texts = []
    for path in APP.rglob("*"):
        if path.is_file() and path.suffix in {".kt", ".xml"}:
            texts.append(read(path))
    all_text = "\n".join(texts)
    assert "WIRELESS_DEBUGGING_SETTINGS" not in all_text
    assert "APPLICATION_DEVELOPMENT_SETTINGS" not in all_text
    assert "adb pair" not in all_text.lower()
    assert "adb connect" not in all_text.lower()


def test_accessibility_control_remains_available_without_adb():
    t = read(JAVA / "HakimAccessibilityService.kt")
    assert "performGlobalAction" in t
    assert "dispatchGesture" in t
    assert "ACTION_SET_TEXT" in t
    assert "takeScreenshot" in t
