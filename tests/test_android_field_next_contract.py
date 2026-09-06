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
    assert 'LOCAL_MODEL_SELECTION' in script
    assert 'BACKGROUND_SURVIVAL_REPAIR' in script
    assert 'http://' not in script
    assert 'https://' not in script


def test_android_field_next_does_not_guess_or_download_a_model():
    script = Path('scripts/android-field-next.sh').read_text(encoding='utf-8')
    lowered = script.lower()
    assert 'curl ' not in lowered
    assert 'wget ' not in lowered
    assert 'huggingface' not in lowered
    assert 'gguf' not in lowered
    assert 'do not choose/download a local model until this exact profile is reviewed' in lowered
