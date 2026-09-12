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


def test_existing_install_requires_same_signing_lineage_before_handoff():
    script = text("scripts/install-android-companion-local.sh")
    assert 'PACKAGE_ID="org.hakim.omega.companion"' in script
    assert 'PM_BIN="/system/bin/pm"' in script
    assert 'list packages "$PACKAGE_ID"' in script
    assert 'path "$PACKAGE_ID"' in script
    assert "Signer #1 certificate SHA-256 digest:" in script
    assert "INSTALLED_SIGNATURE_MISMATCH" in script
    assert "SIGNATURE_CONTINUITY=PROVEN" in script
    assert "refusing to create a replacement key" in script
    assert "parallel_signing_lineage_forbidden" in script
    assert script.index("INSTALLED_SIGNATURE_MISMATCH") < script.index('PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"')


def test_first_install_may_create_owned_key_but_existing_install_cannot_replace_it():
    script = text("scripts/install-android-companion-local.sh")
    guard = 'if [ -n "$INSTALLED_APK" ]; then\n    echo \'ERROR: Hakim is already installed but the owned signing key is missing; refusing to create a replacement key\''
    assert guard in script
    assert "SIGNATURE_CONTINUITY=FIRST_INSTALL" in script
    assert "FIRST_INSTALL_NO_EXISTING_PACKAGE" in script


def test_install_handoff_uses_verified_public_downloads_not_silent_install():
    script = text("scripts/install-android-companion-local.sh")
    assert 'PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"' in script
    assert 'PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"' in script
    assert "public Downloads APK hash mismatch" in script
    assert "OPEN_FILES_APP_AND_TAP=HAKIM-Companion.apk" in script
    assert "adb install" not in script
    assert "pm install" not in script
