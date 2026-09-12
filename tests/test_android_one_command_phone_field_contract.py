from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "scripts" / "hakim-phone-field-run.sh"
INSTALLER = ROOT / "scripts" / "install-android-companion-local.sh"


def test_shell_scripts_parse() -> None:
    subprocess.run(["bash", "-n", str(FLOW)], check=True)
    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)


def test_local_installer_verifies_release_provenance_before_signing() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    verify_pos = text.index("SOURCE_RELEASE_VERIFIED")
    sign_pos = text.index("apksigner sign")
    assert verify_pos < sign_pos
    for required in (
        "hakim-companion-build-manifest.json",
        "source_commit_matches_release",
        "apk_sha_matches_sha_file",
        "apk_sha_matches_manifest",
        "android_tree_recorded",
        "NOT_PROVEN_BY_BUILD",
    ):
        assert required in text
    assert "termux-open --view" in text
    assert "USER_ACTION_REQUIRED=approve Android package installation if prompted" in text


def test_one_command_flow_is_resumable_and_fail_closed() -> None:
    text = FLOW.read_text(encoding="utf-8")
    profile = text.index('bash "$REPO/scripts/android-field-next.sh"')
    install = text.index('bash "$REPO/scripts/install-android-companion-local.sh"')
    pair = text.index('bash "$REPO/scripts/pair-android-companion.sh"')
    gate = text.index('python "$REPO/scripts/android-physical-field-gate.py"')
    assert profile < install < pair < gate
    assert "'field_verified': False" in text
    assert "'promotion_allowed': False" in text
    assert "'secrets_recorded': False" in text
    assert "WAITING_ANDROID_INSTALL_APPROVAL" in text
    assert "PAIR_RETRY_REQUIRED" in text
    assert "PRE_FIELD_PASS" in text
    assert "hakim-phone-field" in text


def test_one_command_flow_preserves_android_user_approval_boundary() -> None:
    text = FLOW.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "android package installer" in lowered
    assert "approve" in lowered
    assert "adb install" not in lowered
    assert "pm install" not in lowered
    assert "settings put secure enabled_accessibility_services" not in lowered
    assert "field_verified=true" not in lowered
    assert "promotion_allowed=true" not in lowered
