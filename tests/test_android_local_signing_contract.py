from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-android-companion-local.sh"


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_local_signing_script_has_valid_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_release_provenance_is_verified_before_signing():
    t = text()
    for token in (
        "hakim-companion-build-manifest.json",
        "RELEASE_DIGEST",
        "UNSIGNED_SOURCE_BUILD_VERIFIED",
        "source_commit_sha",
        "LOCAL_DEVICE_OWNED_KEY_ONLY",
        "BUILD_PROVENANCE=PROVEN",
    ):
        assert token in t
    assert t.index("BUILD_PROVENANCE=PROVEN") < t.index("apksigner sign")


def test_safe_core_source_manifest_is_bound_to_exact_release_commit():
    t = text()
    assert "raw.githubusercontent.com/$REPO/$TARGET_COMMIT/android/hakim-companion/app/src/main/AndroidManifest.xml" in t
    for forbidden in (
        "HakimAccessibilityService",
        "HakimNotificationListener",
        "android.permission.BIND_ACCESSIBILITY_SERVICE",
        "android.service.notification.NotificationListenerService",
        "android.permission.SYSTEM_ALERT_WINDOW",
        "android.permission.REQUEST_INSTALL_PACKAGES",
        "android.permission.READ_SMS",
        "android.permission.READ_CONTACTS",
        "android.permission.READ_CALL_LOG",
        "android.permission.MANAGE_EXTERNAL_STORAGE",
    ):
        assert forbidden in t
    assert "SAFE_CORE_SOURCE_MANIFEST=PROVEN" in t
    assert t.index("SAFE_CORE_SOURCE_MANIFEST=PROVEN") < t.index("apksigner sign")


def test_signer_continuity_is_fail_closed_and_local_only():
    t = text()
    for token in (
        "PREVIOUS_SIGNER",
        "PINNED_SIGNER",
        "hakim-companion.cert.sha256",
        "refusing silent key rotation",
        "signer does not match pinned Hakim certificate",
        "signer changed from previous locally signed Hakim APK",
        "signing_key_location':'LOCAL_DEVICE_ONLY'",
    ):
        assert token in t
    assert "apksigner verify --verbose --print-certs" in t
    assert "--ks \"$KEYSTORE\"" in t


def test_signed_handoff_is_hashed_and_field_claim_stays_fail_closed():
    t = text()
    assert "physical_installation':'NOT_PROVEN_UNTIL_ANDROID_INSTALLS_THIS_APK'" in t
    assert "PUBLIC_SHA" in t and "SIGNED_SHA" in t
    assert "HAKIM-Companion.provenance.json" in t
    assert "termux-open --view \"$PUBLIC_APK\"" in t
