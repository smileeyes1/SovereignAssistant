from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-android-companion-local.sh"


def test_installer_script_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_signed_apk_is_handed_to_public_downloads_with_hash_check() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'PUBLIC_DOWNLOADS="$HOME_DIR/storage/downloads"' in text
    assert 'PUBLIC_APK="$PUBLIC_DOWNLOADS/HAKIM-Companion.apk"' in text
    assert 'cp -f "$SIGNED" "$PUBLIC_APK"' in text
    assert 'PUBLIC_SHA="$(sha256sum "$PUBLIC_APK"' in text
    assert 'SIGNED_SHA="$(sha256sum "$SIGNED"' in text
    assert 'public Downloads APK hash mismatch' in text


def test_private_termux_uri_is_not_auto_opened() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'termux-open --view --content-type application/vnd.android.package-archive "$SIGNED"' not in text
