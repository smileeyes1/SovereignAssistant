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
    assert 'ANDROID_COMPANION_LOCAL_INSTALL' in script
    assert 'BACKGROUND_SURVIVAL_REPAIR' in script
    assert 'http://' not in script
    assert 'https://' not in script


def test_android_field_next_preserves_companion_first_and_no_resident_model_policy():
    script = Path('scripts/android-field-next.sh').read_text(encoding='utf-8')
    lowered = script.lower()
    assert 'local_model_selection' not in lowered
    assert 'local inference is optional and on-demand only after core companion field qualification' in lowered
    assert 'never keep a resident local model' in lowered
    assert 'never use a local llm for autonomous planning' in lowered
    assert 'stop any on-demand model immediately after the bounded request' in lowered
    assert 'curl ' not in lowered
    assert 'wget ' not in lowered
    assert 'huggingface' not in lowered
    assert 'gguf' not in lowered
