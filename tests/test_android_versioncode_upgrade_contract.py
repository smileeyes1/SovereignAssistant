from pathlib import Path
import re

BUILD = Path('android/hakim-companion/app/build.gradle.kts').read_text(encoding='utf-8')


def test_android_versioncode_exceeds_installed_legacy_20017():
    m = re.search(r'versionCode\s*=\s*(\d+)', BUILD)
    assert m, 'versionCode missing'
    assert int(m.group(1)) > 20017, 'Android update must not be a downgrade versus installed 20017'


def test_application_id_remains_stable_for_in_place_update():
    assert 'applicationId = "org.hakim.omega.companion"' in BUILD
