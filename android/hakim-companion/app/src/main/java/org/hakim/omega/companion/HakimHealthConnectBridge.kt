package org.hakim.omega.companion

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregateRequest
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import kotlin.math.roundToLong

object HakimHealthConnectBridge {
    val readPermissions: Set<String> = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class)
    )

    fun availability(context: Context): Int = HealthConnectClient.getSdkStatus(context)

    fun availabilityText(context: Context): String = when (availability(context)) {
        HealthConnectClient.SDK_AVAILABLE -> "متاح"
        HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "يحتاج تحديثًا/موفرًا"
        else -> "غير متاح"
    }

    suspend fun hasReadPermissions(context: Context): Boolean {
        if (availability(context) != HealthConnectClient.SDK_AVAILABLE) return false
        val client = HealthConnectClient.getOrCreate(context)
        return client.permissionController.getGrantedPermissions().containsAll(readPermissions)
    }

    suspend fun readLast24Hours(context: Context): JSONObject {
        require(availability(context) == HealthConnectClient.SDK_AVAILABLE) {
            "Health Connect غير متاح على هذا الجهاز"
        }
        val client = HealthConnectClient.getOrCreate(context)
        val granted = client.permissionController.getGrantedPermissions()
        require(granted.containsAll(readPermissions)) {
            "لم تُمنح أذونات قراءة النبض والخطوات"
        }

        val end = Instant.now()
        val start = end.minus(Duration.ofHours(24))
        val filter = TimeRangeFilter.between(start, end)

        val heartResponse = client.readRecords(
            ReadRecordsRequest(
                HeartRateRecord::class,
                timeRangeFilter = filter
            )
        )
        val samples = heartResponse.records
            .flatMap { it.samples }
            .sortedBy { it.time }

        val bpmValues = samples.map { it.beatsPerMinute }
        val latestBpm = samples.lastOrNull()?.beatsPerMinute
        val averageBpm = if (bpmValues.isEmpty()) null else bpmValues.average().roundToLong()
        val minBpm = bpmValues.minOrNull()
        val maxBpm = bpmValues.maxOrNull()

        val stepAggregate = client.aggregate(
            AggregateRequest(
                metrics = setOf(StepsRecord.COUNT_TOTAL),
                timeRangeFilter = filter
            )
        )
        val steps = stepAggregate[StepsRecord.COUNT_TOTAL] ?: 0L

        return JSONObject()
            .put("schema", "HAKIM_HEALTH_READONLY_V1")
            .put("window_start", start.toString())
            .put("window_end", end.toString())
            .put("heart_rate", JSONObject()
                .put("sample_count", samples.size)
                .put("latest_bpm", latestBpm ?: JSONObject.NULL)
                .put("average_bpm", averageBpm ?: JSONObject.NULL)
                .put("min_bpm", minBpm ?: JSONObject.NULL)
                .put("max_bpm", maxBpm ?: JSONObject.NULL))
            .put("steps", steps)
            .put("diagnostic", false)
            .put("medical_device_control", false)
            .put("persisted", false)
    }

    fun humanSummary(snapshot: JSONObject): String {
        val heart = snapshot.getJSONObject("heart_rate")
        val latest = if (heart.isNull("latest_bpm")) "لا توجد قراءة" else "${heart.getLong("latest_bpm")} نبضة/دقيقة"
        val avg = if (heart.isNull("average_bpm")) "—" else heart.getLong("average_bpm").toString()
        val min = if (heart.isNull("min_bpm")) "—" else heart.getLong("min_bpm").toString()
        val max = if (heart.isNull("max_bpm")) "—" else heart.getLong("max_bpm").toString()
        return "آخر ٢٤ ساعة:\n" +
            "النبض الأحدث: $latest\n" +
            "متوسط/أدنى/أعلى النبض: $avg / $min / $max\n" +
            "الخطوات: ${snapshot.getLong("steps")}\n" +
            "هذه قراءة معلوماتية فقط وليست تشخيصًا طبيًا."
    }
}
