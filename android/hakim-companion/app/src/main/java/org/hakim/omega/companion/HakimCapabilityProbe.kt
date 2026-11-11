package org.hakim.omega.companion

import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorManager
import android.os.Build
import androidx.health.connect.client.HealthConnectClient
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

object HakimCapabilityProbe {
    private const val PREFS = "hakim_capabilities"
    private const val KEY_LAST = "last_snapshot"

    fun probe(context: Context): JSONObject {
        val pm = context.packageManager
        val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val features = linkedMapOf(
            "bluetooth" to PackageManager.FEATURE_BLUETOOTH,
            "bluetooth_le" to PackageManager.FEATURE_BLUETOOTH_LE,
            "wifi" to PackageManager.FEATURE_WIFI,
            "wifi_direct" to PackageManager.FEATURE_WIFI_DIRECT,
            "nfc" to PackageManager.FEATURE_NFC,
            "usb_host" to PackageManager.FEATURE_USB_HOST,
            "consumer_ir" to PackageManager.FEATURE_CONSUMER_IR,
            "camera_any" to PackageManager.FEATURE_CAMERA_ANY,
            "microphone" to PackageManager.FEATURE_MICROPHONE,
            "gps" to PackageManager.FEATURE_LOCATION_GPS,
            "companion_device_setup" to PackageManager.FEATURE_COMPANION_DEVICE_SETUP,
            "uwb" to "android.hardware.uwb"
        )

        val featureJson = JSONObject()
        features.forEach { (id, feature) -> featureJson.put(id, pm.hasSystemFeature(feature)) }

        val sensors = JSONArray()
        sensorManager.getSensorList(Sensor.TYPE_ALL)
            .sortedWith(compareBy<Sensor> { it.type }.thenBy { it.name })
            .forEach { sensor ->
                sensors.put(
                    JSONObject()
                        .put("type", sensor.type)
                        .put("name", sensor.name)
                        .put("vendor", sensor.vendor)
                        .put("version", sensor.version)
                        .put("resolution", sensor.resolution.toDouble())
                        .put("max_range", sensor.maximumRange.toDouble())
                        .put("power_ma", sensor.power.toDouble())
                        .put("min_delay_us", sensor.minDelay)
                        .put("wake_up", if (Build.VERSION.SDK_INT >= 21) sensor.isWakeUpSensor else false)
                )
            }

        val healthStatus = runCatching { HealthConnectClient.getSdkStatus(context) }
            .getOrDefault(HealthConnectClient.SDK_UNAVAILABLE)
        val healthText = when (healthStatus) {
            HealthConnectClient.SDK_AVAILABLE -> "AVAILABLE"
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "UPDATE_REQUIRED"
            else -> "UNAVAILABLE"
        }

        return JSONObject()
            .put("schema", "HAKIM_CAPABILITY_SNAPSHOT_V1")
            .put("captured_at", Instant.now().toString())
            .put("android_sdk", Build.VERSION.SDK_INT)
            .put("device", JSONObject()
                .put("manufacturer", Build.MANUFACTURER)
                .put("model", Build.MODEL)
                .put("product", Build.PRODUCT))
            .put("features", featureJson)
            .put("sensors", sensors)
            .put("health_connect", JSONObject()
                .put("status", healthText)
                .put("read_only_initial_scope", JSONArray(listOf("HEART_RATE", "STEPS")))
                .put("field_verified", false))
            .put("root_required_for_probe", false)
            .put("field_verified", false)
    }

    fun probeAndPersist(context: Context): JSONObject {
        val snapshot = probe(context)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LAST, snapshot.toString())
            .apply()
        return snapshot
    }

    fun lastSnapshot(context: Context): JSONObject? {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_LAST, null) ?: return null
        return runCatching { JSONObject(raw) }.getOrNull()
    }

    fun summary(context: Context): String {
        val snapshot = lastSnapshot(context) ?: probeAndPersist(context)
        val features = snapshot.getJSONObject("features")
        val sensors = snapshot.getJSONArray("sensors")
        val hc = snapshot.getJSONObject("health_connect").getString("status")
        val enabled = features.keys().asSequence().count { features.optBoolean(it, false) }
        return "القدرات: $enabled اتصال/ميزة متاحة، ${sensors.length()} حساسًا مُكتشفًا، Health Connect: $hc — فحص وجود فقط وليس تحققًا طبيًا أو ميدانيًا"
    }
}
