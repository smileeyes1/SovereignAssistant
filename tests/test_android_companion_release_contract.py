from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_is_unsigned_and_repository_has_no_signing_secret():
    wf = text(".github/workflows/android-companion-release.yml")
    assert ":app:assembleRelease" in wf
    assert "app-release-unsigned.apk" in wf
    assert "hakim-companion-unsigned.apk" in wf
    assert "keystore" not in wf.casefold()
    assert "storepass" not in wf.casefold()


def test_phone_owns_stable_signing_key_and_verifies_source_hash():
    script = text("scripts/install-android-companion-local.sh")
    assert "$HOME_DIR/.omega/keys" in script
    assert "chmod 600" in script
    assert "sha256sum -c" in script
    assert "apksigner sign" in script
    assert "apksigner verify" in script
    assert "keytool -genkeypair" in script
    assert "secrets.token_urlsafe" in script
    assert "LOCAL_DEVICE_ONLY" in script


def test_install_handoff_uses_verified_public_downloads_not_silent_install():
    script = text("scripts/install-android-companion-local.sh")
    assert 'PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"' in script
    assert 'PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"' in script
    assert "public Downloads APK hash mismatch" in script
    assert "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk" in script
    assert "adb install" not in script
    assert "pm install" not in script
