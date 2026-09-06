from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-android-autonomy.sh"


def test_full_upgrade_precedes_node_install() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    upgrade = text.index("full-upgrade -y")
    node_install = text.index("pkg install -y python git cmake clang make curl termux-api nodejs tmux")
    assert upgrade < node_install


def test_installer_records_exact_android_device_identity() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for key in (
        "ro.product.manufacturer",
        "ro.product.model",
        "ro.build.version.release",
        "ro.build.version.sdk",
        "ro.product.cpu.abi",
        ".omega/device.json",
    ):
        assert key in text


def test_remote_bridge_is_persistent_but_optional() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--persist-session" in text
    assert "tmux new-session -d -s dc" in text
    assert "optional temporary remote bridge" in text.lower()
    assert "remote bridge is NOT required" in text


def test_android_background_hardening_helper_exists() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "open-hakim-background-settings" in text
    assert "android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS" in text


def test_helper_commands_are_exposed_on_termux_path() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'ln -sfn "$HOME/bin/$tool" "$PREFIX/bin/$tool"' in text
    for tool in (
        "hakim-android",
        "hakim-approval-test",
        "pair-chatgpt-device",
        "open-hakim-permissions",
        "open-hakim-background-settings",
    ):
        assert f'command -v "$tool"' in text or tool in text
