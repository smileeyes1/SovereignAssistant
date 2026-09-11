from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-android-companion-local.sh"


def test_local_signer_script_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_apksigner_uses_distinct_password_sources() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'KS_PASS_SOURCE="$(mktemp' in text
    assert 'KEY_PASS_SOURCE="$(mktemp' in text
    assert '--ks-pass "file:$KS_PASS_SOURCE"' in text
    assert '--key-pass "file:$KEY_PASS_SOURCE"' in text
    assert '--ks-pass "file:$PASSFILE"' not in text
    assert '--key-pass "file:$PASSFILE"' not in text
    assert 'trap cleanup_password_sources EXIT INT TERM' in text


def test_durable_password_and_keystore_remain_device_owned() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'PASSFILE="$KEY_DIR/hakim-companion.pass"' in text
    assert 'KEYSTORE="$KEY_DIR/hakim-companion.jks"' in text
    assert "chmod 600 \"$PASSFILE\"" in text
    assert "chmod 600 \"$KEYSTORE\"" in text
