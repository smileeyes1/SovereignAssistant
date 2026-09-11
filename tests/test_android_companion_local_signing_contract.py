from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-android-companion-local.sh"


def test_local_signer_script_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_apksigner_uses_one_password_file_read() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    executable_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert 'KS_PASS_SOURCE="$(mktemp' in text
    assert '--ks-pass "file:$KS_PASS_SOURCE"' in text
    assert all('--key-pass' not in line for line in executable_lines)
    assert '--ks-pass "file:$PASSFILE"' not in text
    assert 'trap cleanup_password_source EXIT INT TERM' in text


def test_keystore_key_passwords_are_intentionally_identical() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '-storepass "$PASS" -keypass "$PASS"' in text


def test_durable_password_and_keystore_remain_device_owned() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'PASSFILE="$KEY_DIR/hakim-companion.pass"' in text
    assert 'KEYSTORE="$KEY_DIR/hakim-companion.jks"' in text
    assert "chmod 600 \"$PASSFILE\"" in text
    assert "chmod 600 \"$KEYSTORE\"" in text
