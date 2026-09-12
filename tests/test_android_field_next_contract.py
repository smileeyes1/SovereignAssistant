from pathlib import Path


def test_android_field_next_is_local_only_and_collects_required_evidence():
    script = Path('scripts/android-field-next.sh').read_text(encoding='utf-8')
    assert 'hakim-android background-test status' in script
    assert 'ro.product.manufacturer' in script
    assert 'ro.product.model' in script
    assert 'ro.build.version.release' in script
    assert 'ro.build.version.sdk' in script
    assert 'ro.product.cpu.abi' in script
    assert '/proc/meminfo' in script
    assert 'home_available_gib' in script
    assert 'TERMUX_APP__APK_RELEASE' in script
    assert 'device-field-profile.json' in script
    assert "next_gate='TERMUX_ADB_REAL_FIELD_ROUND_TRIP'" in script
    assert "next_gate='ANDROID_WIRELESS_DEBUGGING_PAIRING'" in script
    assert "'field_path': 'TERMUX_WIRELESS_ADB_LOCAL'" in script
    assert "'post_field_candidate': 'ANDROID_COMPANION_NO_ADB_RUNTIME'" in script
    assert 'BACKGROUND_SURVIVAL_REPAIR' not in script
    assert 'BACKGROUND_SURVIVAL_EVIDENCE' not in script
    assert 'http://' not in script
    assert 'https://' not in script


def test_android_field_next_preserves_no_resident_model_and_no_premature_promotion():
    script = Path('scripts/android-field-next.sh').read_text(encoding='utf-8')
    lowered = script.lower()
    assert 'local_model_selection' not in lowered
    assert 'diagnostic_until_real_field_matrix' in lowered
    assert 'never retire adb' in lowered
    assert 'companion-only real round trip' in lowered
    assert 'local inference is optional and on-demand only after core device qualification' in lowered
    assert 'never keep a resident local model' in lowered
    assert 'never use a local llm for autonomous planning' in lowered
    assert 'curl ' not in lowered
    assert 'wget ' not in lowered
    assert 'huggingface' not in lowered
    assert 'gguf' not in lowered
