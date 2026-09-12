import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_android_update_preserves_single_installed_package_identity():
    gradle = text("android/hakim-companion/app/build.gradle.kts")
    assert 'applicationId = "org.hakim.omega.companion"' in gradle
    assert "versionCode = 8" in gradle
    assert 'versionName = "0.5.0-canonical-phone-interface-native-adb"' in gradle


def test_installed_ui_declares_canonical_hakim_and_preserves_native_adb():
    identity = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/CanonicalHakimIdentity.kt")
    main = text("android/hakim-companion/app/src/main/java/org/hakim/omega/companion/MainActivity.kt")
    manifest = text("android/hakim-companion/app/src/main/AndroidManifest.xml")
    assert 'INSTANCE_ID = "HAKIM_ORIGINAL_PHONE_APP"' in identity
    assert 'INSTALLED_INTERFACE_ROLE = "PRIMARY_INSTALLED_INTERFACE_OF_SINGLE_HAKIM"' in identity
    assert 'ANDROID_APPLICATION_ID = "org.hakim.omega.companion"' in identity
    assert 'RUNTIME_REPOSITORY = "smileeyes1/SovereignAssistant"' in identity
    assert "CanonicalHakimIdentity.DISPLAY_NAME_AR" in main
    assert "ليست حكيمًا ثانيًا" in main
    assert "HakimLocalPairing.openWirelessDebuggingSettings" in main
    assert 'android:label="حكيم"' in manifest
    assert "HakimPairingReceiver" in manifest
    assert "HAKIM Ω Companion" not in manifest


def test_active_pointer_names_identity_without_mutating_frozen_restore_contract():
    active = json.loads(text("governance/HAKIM_ACTIVE.json"))
    spec = json.loads(text(active["phone_interface_identity"]))
    assert active["version"] == "2.3"
    assert "LOAD_PHONE_INTERFACE_IDENTITY" not in active["restore_sequence"]
    assert "PHONE_INTERFACE_IDENTITY_CONTRACT_PASS" not in active["promotion_gate"]
    assert spec["canonical_instance_id"] == "HAKIM_ORIGINAL_PHONE_APP"
    assert spec["android_application_id"] == "org.hakim.omega.companion"
    assert spec["upgrade_in_place_required"] is True
    assert spec["parallel_hakim_forbidden"] is True
    assert spec["phone_interface_is_same_hakim"] is True
    assert spec["native_local_adb_must_be_preserved"] is True
    assert spec["field_verified"] is False
