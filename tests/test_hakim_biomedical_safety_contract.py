from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android/hakim-companion/app/src/main"
MANIFEST = ANDROID / "AndroidManifest.xml"
KOTLIN = ANDROID / "java/org/hakim/omega/companion"
HEALTH_BRIDGE = KOTLIN / "HakimHealthConnectBridge.kt"
HEALTH_ACTIVITY = KOTLIN / "HakimHealthActivity.kt"
HEALTH_QUALIFICATION = KOTLIN / "HakimHealthFieldQualification.kt"
SENSOR_QUALIFICATION = KOTLIN / "HakimSensorFieldQualification.kt"
POLICY = ROOT / "governance/HAKIM_BIOMEDICAL_SAFETY_POLICY_v1.json"


def test_health_permissions_are_read_only_and_minimal():
    text = MANIFEST.read_text(encoding="utf-8")
    assert 'android.permission.health.READ_HEART_RATE' in text
    assert 'android.permission.health.READ_STEPS' in text
    forbidden = [
        'android.permission.health.WRITE_',
        'android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND',
        'android.permission.health.READ_HEALTH_DATA_HISTORY',
    ]
    for token in forbidden:
        assert token not in text, f"forbidden health permission present: {token}"


def test_health_connect_privacy_rationale_is_declared():
    text = MANIFEST.read_text(encoding="utf-8")
    assert 'androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE' in text
    assert 'android.intent.action.VIEW_PERMISSION_USAGE' in text
    assert 'android.intent.category.HEALTH_PERMISSIONS' in text
    assert 'android.permission.START_VIEW_PERMISSION_USAGE' in text


def test_health_bridge_has_no_write_or_delete_path():
    text = HEALTH_BRIDGE.read_text(encoding="utf-8")
    forbidden = [
        'getWritePermission',
        'insertRecords(',
        'updateRecords(',
        'deleteRecords(',
        'PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND',
        'PERMISSION_READ_HEALTH_DATA_HISTORY',
    ]
    for token in forbidden:
        assert token not in text, f"forbidden Health Connect operation present: {token}"
    assert 'getReadPermission(HeartRateRecord::class)' in text
    assert 'getReadPermission(StepsRecord::class)' in text


def test_field_qualification_proves_read_then_revocation_fail_closed():
    activity = HEALTH_ACTIVITY.read_text(encoding="utf-8")
    qualification = HEALTH_QUALIFICATION.read_text(encoding="utf-8")
    assert 'PermissionController.createRequestPermissionResultContract()' in activity
    assert 'runReadQualification()' in activity
    assert 'HakimHealthFieldQualification.beginRevocationTest(this)' in activity
    assert 'HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS' in activity
    assert '!HakimHealthConnectBridge.hasReadPermissions' in activity
    assert 'HakimHealthConnectBridge.readLast24Hours' in activity
    assert '.isFailure' in activity
    assert 'markRevocationProven' in activity
    assert 'readProven(context) && revocationProven(context)' in qualification


def test_qualification_log_does_not_persist_raw_health_values():
    text = HEALTH_QUALIFICATION.read_text(encoding="utf-8")
    assert 'sample_count' in text
    assert 'latest_bpm' not in text
    assert 'average_bpm' not in text
    assert 'min_bpm' not in text
    assert 'max_bpm' not in text
    assert '"steps"' not in text
    assert 'KEY_HEART_SOURCE_PRESENT' in text


def test_sensor_field_qualification_uses_safe_types_and_no_raw_values():
    sensor = SENSOR_QUALIFICATION.read_text(encoding="utf-8")
    activity = HEALTH_ACTIVITY.read_text(encoding="utf-8")
    for token in [
        'Sensor.TYPE_ACCELEROMETER',
        'Sensor.TYPE_LIGHT',
        'Sensor.TYPE_PROXIMITY',
        'Sensor.TYPE_PRESSURE',
        'Sensor.TYPE_MAGNETIC_FIELD',
    ]:
        assert token in sensor
    assert 'raw_values_persisted", false' in sensor
    assert 'event.values' not in sensor
    assert 'manager.unregisterListener(listener)' in sensor
    assert 'HakimSensorFieldQualification.run(this)' in activity
    assert 'HakimCapabilityProbe.probeAndPersist(this)' in activity


def test_biomedical_policy_fails_closed_for_direct_intervention():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["principles"]["root_never_overrides_medical_policy"] is True
    assert policy["health_connect"]["write_permissions"] is False
    assert policy["health_connect"]["background_read"] is False
    assert policy["health_connect"]["history_over_30_days"] is False
    assert policy["r3_policy"]["general_hakim_autonomy"] == "DENY"
    forbidden = set(policy["forbidden_autonomous_actions"])
    required = {
        "CHANGE_MEDICATION_OR_DOSAGE",
        "DELIVER_ELECTRICAL_STIMULATION_TO_HUMAN",
        "CONTROL_PACEMAKER",
        "CONTROL_ICD",
        "CONTROL_ANY_IMPLANTED_MEDICAL_DEVICE",
        "USE_ROOT_TO_BYPASS_MEDICAL_OR_PRIVACY_GUARDS",
    }
    assert required <= forbidden


def test_capability_probe_never_claims_field_verification():
    probe = (KOTLIN / "HakimCapabilityProbe.kt").read_text(encoding="utf-8")
    assert '.put("field_verified", false)' in probe
    assert '.put("root_required_for_probe", false)' in probe
