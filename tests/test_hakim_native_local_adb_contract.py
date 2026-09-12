from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "hakim-companion" / "app"
SRC = APP / "src" / "main" / "java" / "org" / "hakim" / "omega" / "companion"


def test_native_pairing_is_inside_hakim_and_external_helpers_are_not_required():
    pairing = (SRC / "HakimLocalPairing.kt").read_text(encoding="utf-8")
    manager = (SRC / "HakimAdbConnectionManager.kt").read_text(encoding="utf-8")
    manifest = (APP / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")

    assert "RemoteInput" in pairing
    assert "SERVICE_TYPE_TLS_PAIRING" in manager
    assert 'KeyStore.getInstance("AndroidKeyStore")' in manager
    assert "HakimPairingReceiver" in manifest
    assert "AccessibilityService" not in manifest.replace("does not require AccessibilityService", "")
    assert "NotificationListenerService" not in manifest.replace("NotificationListenerService", "")


def test_pairing_accepts_only_six_digits_and_auto_discovers_port():
    pairing = (SRC / "HakimLocalPairing.kt").read_text(encoding="utf-8")
    manager = (SRC / "HakimAdbConnectionManager.kt").read_text(encoding="utf-8")

    assert 'Regex("^[0-9]{6}$")' in pairing
    assert 'Regex("^[0-9]{6}$")' in manager
    assert "AdbMdns.SERVICE_TYPE_TLS_PAIRING" in manager
    assert "autoConnect" in manager


def test_release_does_not_claim_field_verified():
    activity = (SRC / "MainActivity.kt").read_text(encoding="utf-8")
    assert "التحكم الأوسع لا يُدّعى قبل التأهيل الميداني" in activity
