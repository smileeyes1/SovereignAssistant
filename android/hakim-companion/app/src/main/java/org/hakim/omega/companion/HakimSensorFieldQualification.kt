package org.hakim.omega.companion

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean

object HakimSensorFieldQualification {
    private const val PREFS = "hakim_sensor_field_qualification"
    private const val KEY_SUMMARY = "summary"
    private const val KEY_PROVEN = "stream_proven"

    private val safeTypes = listOf(
        Sensor.TYPE_ACCELEROMETER,
        Sensor.TYPE_LIGHT,
        Sensor.TYPE_PROXIMITY,
        Sensor.TYPE_PRESSURE,
        Sensor.TYPE_MAGNETIC_FIELD
    )

    fun run(context: Context, durationMs: Long = 2500L, onComplete: (String) -> Unit) {
        val manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensors = safeTypes.mapNotNull { manager.getDefaultSensor(it) }
        if (sensors.isEmpty()) {
            persist(context, JSONObject().put("status", "NO_SAFE_TARGET_SENSOR_PRESENT").put("captured_at", Instant.now().toString()), false)
            onComplete(summary(context))
            return
        }

        val counts = linkedMapOf<Int, Int>()
        sensors.forEach { counts[it.type] = 0 }
        val finished = AtomicBoolean(false)
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                if (!finished.get()) counts[event.sensor.type] = (counts[event.sensor.type] ?: 0) + 1
            }
            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }

        sensors.forEach { manager.registerListener(listener, it, SensorManager.SENSOR_DELAY_NORMAL) }
        Handler(Looper.getMainLooper()).postDelayed({
            if (!finished.compareAndSet(false, true)) return@postDelayed
            manager.unregisterListener(listener)
            val result = JSONObject()
                .put("status", "COMPLETED")
                .put("captured_at", Instant.now().toString())
                .put("raw_values_persisted", false)
            val events = JSONObject()
            counts.forEach { (type, count) -> events.put(type.toString(), count) }
            result.put("event_counts_by_sensor_type", events)
            val proven = counts.values.any { it > 0 }
            persist(context, result, proven)
            onComplete(summary(context))
        }, durationMs)
    }

    fun proven(context: Context): Boolean = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        .getBoolean(KEY_PROVEN, false)

    fun summary(context: Context): String {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = p.getString(KEY_SUMMARY, null) ?: return "تأهيل الحساسات: لم يُنفذ ميدانيًا بعد"
        val obj = runCatching { JSONObject(raw) }.getOrNull() ?: return "تأهيل الحساسات: سجل غير صالح"
        val events = obj.optJSONObject("event_counts_by_sensor_type")
        val total = events?.keys()?.asSequence()?.sumOf { events.optInt(it, 0) } ?: 0
        return "تأهيل الحساسات: ${if (proven(context)) "بث فعلي مثبت" else "غير مثبت"}، أحداث مستلمة=$total، القيم الخام غير محفوظة"
    }

    private fun persist(context: Context, result: JSONObject, proven: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_SUMMARY, result.toString())
            .putBoolean(KEY_PROVEN, proven)
            .apply()
    }
}
