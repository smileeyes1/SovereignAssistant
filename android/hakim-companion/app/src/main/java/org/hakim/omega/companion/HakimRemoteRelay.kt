package org.hakim.omega.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Base64
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Outbound-only remote transport for HAKIM Companion.
 *
 * Security invariants:
 * - never opens a non-loopback listener;
 * - remote state-changing operations require an explicit Android approval;
 * - request ids are claimed before execution to prevent replay;
 * - expired requests fail closed;
 * - the existing pair token remains local and is only used against 127.0.0.1.
 */
class HakimRemoteRelay(private val context: Context) {
    private val executor = Executors.newSingleThreadExecutor()
    private val running = AtomicBoolean(false)

    fun start() {
        if (!running.compareAndSet(false, true)) return
        ensureApprovalChannel(context)
        executor.execute { loop() }
    }

    fun stop() {
        running.set(false)
        executor.shutdownNow()
    }

    private fun loop() {
        var retryMs = 2_000L
        while (running.get()) {
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val topic = prefs.getString(KEY_TOPIC, null)
            val resultUrl = prefs.getString(KEY_RESULT_URL, null)
            if (topic.isNullOrBlank() || resultUrl.isNullOrBlank()) {
                sleep(10_000L)
                continue
            }
            try {
                val url = URL("https://ntfy.sh/$topic/json")
                val conn = url.openConnection() as HttpURLConnection
                conn.connectTimeout = 15_000
                conn.readTimeout = 75_000
                conn.requestMethod = "GET"
                conn.setRequestProperty("Accept", "application/x-ndjson")
                conn.inputStream.use { input ->
                    BufferedReader(InputStreamReader(input, Charsets.UTF_8)).use { reader ->
                        retryMs = 2_000L
                        while (running.get()) {
                            val line = reader.readLine() ?: break
                            handleNtfyLine(line, resultUrl)
                        }
                    }
                }
                conn.disconnect()
            } catch (_: Exception) {
                sleep(retryMs)
                retryMs = (retryMs * 2).coerceAtMost(60_000L)
            }
        }
    }

    private fun handleNtfyLine(line: String, resultUrl: String) {
        val event = runCatching { JSONObject(line) }.getOrNull() ?: return
        if (event.optString("event") != "message") return
        val encoded = event.optString("message").trim()
        val raw = runCatching {
            String(Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING), Charsets.UTF_8)
        }.getOrNull() ?: return
        val envelope = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val requestId = envelope.optString("request_id")
        val op = envelope.optString("op")
        val expiresAt = envelope.optLong("expires_at_ms", 0L)
        if (!REQUEST_ID.matches(requestId) || !ALLOWED_OPS.contains(op)) return
        if (expiresAt <= System.currentTimeMillis()) {
            sendResult(resultUrl, requestId, "expired", JSONObject().put("error", "request_expired"))
            return
        }
        if (!claimRemoteRequest(context, requestId)) {
            sendResult(resultUrl, requestId, "duplicate", JSONObject().put("error", "duplicate_request"))
            return
        }
        if (READ_ONLY_OPS.contains(op)) {
            val result = executeEnvelope(context, envelope)
            sendResult(resultUrl, requestId, if (result.optBoolean("ok", false)) "ok" else "error", result)
        } else {
            savePending(context, envelope, resultUrl)
            showApproval(context, requestId, op)
        }
    }

    private fun sleep(ms: Long) {
        try { Thread.sleep(ms) } catch (_: InterruptedException) { Thread.currentThread().interrupt() }
    }

    companion object {
        const val PREFS = "hakim"
        const val KEY_TOPIC = "relay_topic"
        const val KEY_RESULT_URL = "relay_result_url"
        private const val APPROVAL_CHANNEL = "hakim_remote_approval"
        private const val ACTION_APPROVE = "org.hakim.omega.companion.REMOTE_APPROVE"
        private const val ACTION_REJECT = "org.hakim.omega.companion.REMOTE_REJECT"
        private const val EXTRA_REQUEST_ID = "request_id"
        private val REQUEST_ID = Regex("^[A-Za-z0-9._:-]{8,128}$")
        private val READ_ONLY_OPS = setOf("status", "ui", "notifications", "screenshot")
        private val ALLOWED_OPS = READ_ONLY_OPS + setOf("action", "launch")

        fun configure(context: Context, topic: String?, resultUrl: String?) {
            if (topic.isNullOrBlank() || !Regex("^[A-Za-z0-9_-]{20,120}$").matches(topic)) return
            if (resultUrl.isNullOrBlank() || !resultUrl.startsWith("https://")) return
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_TOPIC, topic)
                .putString(KEY_RESULT_URL, resultUrl)
                .apply()
        }

        private fun claimRemoteRequest(context: Context, requestId: String): Boolean {
            val prefs = context.getSharedPreferences("hakim_remote_idempotency", Context.MODE_PRIVATE)
            if (prefs.contains(requestId)) return false
            return prefs.edit().putLong(requestId, System.currentTimeMillis()).commit()
        }

        private fun savePending(context: Context, envelope: JSONObject, resultUrl: String) {
            val id = envelope.optString("request_id")
            context.getSharedPreferences("hakim_remote_pending", Context.MODE_PRIVATE).edit()
                .putString("$id.envelope", envelope.toString())
                .putString("$id.result_url", resultUrl)
                .apply()
        }

        private fun takePending(context: Context, requestId: String): Pair<JSONObject, String>? {
            val prefs = context.getSharedPreferences("hakim_remote_pending", Context.MODE_PRIVATE)
            val raw = prefs.getString("$requestId.envelope", null) ?: return null
            val url = prefs.getString("$requestId.result_url", null) ?: return null
            prefs.edit().remove("$requestId.envelope").remove("$requestId.result_url").apply()
            return runCatching { JSONObject(raw) to url }.getOrNull()
        }

        private fun showApproval(context: Context, requestId: String, op: String) {
            ensureApprovalChannel(context)
            val approve = PendingIntent.getBroadcast(
                context, requestId.hashCode(),
                Intent(context, RemoteApprovalReceiver::class.java).setAction(ACTION_APPROVE).putExtra(EXTRA_REQUEST_ID, requestId),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val reject = PendingIntent.getBroadcast(
                context, requestId.hashCode() xor 0x55AA,
                Intent(context, RemoteApprovalReceiver::class.java).setAction(ACTION_REJECT).putExtra(EXTRA_REQUEST_ID, requestId),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notification = android.app.Notification.Builder(context, APPROVAL_CHANNEL)
                .setContentTitle("حكيم — موافقة مطلوبة")
                .setContentText("طلب تحكم على الهاتف: $op")
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setAutoCancel(true)
                .addAction(android.R.drawable.ic_input_add, "موافقة", approve)
                .addAction(android.R.drawable.ic_delete, "رفض", reject)
                .build()
            context.getSystemService(NotificationManager::class.java).notify(requestId.hashCode(), notification)
        }

        fun handleApproval(context: Context, requestId: String, approved: Boolean) {
            val pending = takePending(context, requestId) ?: return
            val (envelope, resultUrl) = pending
            if (!approved) {
                sendResult(resultUrl, requestId, "rejected", JSONObject().put("ok", false).put("error", "rejected_by_user"))
                return
            }
            val expiresAt = envelope.optLong("expires_at_ms", 0L)
            if (expiresAt <= System.currentTimeMillis()) {
                sendResult(resultUrl, requestId, "expired", JSONObject().put("ok", false).put("error", "request_expired"))
                return
            }
            Executors.newSingleThreadExecutor().execute {
                val result = executeEnvelope(context, envelope)
                sendResult(resultUrl, requestId, if (result.optBoolean("ok", false)) "ok" else "error", result)
            }
        }

        private fun executeEnvelope(context: Context, envelope: JSONObject): JSONObject {
            val requestId = envelope.optString("request_id")
            val op = envelope.optString("op")
            return when (op) {
                "status" -> localRequest(context, "GET", "/v1/status", null, null)
                "ui" -> localRequest(context, "GET", "/v1/ui", null, null)
                "notifications" -> localRequest(context, "GET", "/v1/notifications", null, null)
                "screenshot" -> localRequest(context, "GET", "/v1/screenshot", null, null)
                "action" -> localRequest(context, "POST", "/v1/action", envelope.optJSONObject("payload") ?: JSONObject(), requestId)
                "launch" -> localRequest(context, "POST", "/v1/launch", envelope.optJSONObject("payload") ?: JSONObject(), requestId)
                else -> JSONObject().put("ok", false).put("error", "unsupported_operation")
            }
        }

        private fun localRequest(context: Context, method: String, path: String, body: JSONObject?, requestId: String?): JSONObject {
            val token = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("pair_token", null)
                ?: return JSONObject().put("ok", false).put("error", "not_paired")
            return try {
                val conn = URL("http://127.0.0.1:${LocalControlServer.PORT}$path").openConnection() as HttpURLConnection
                conn.connectTimeout = 4_000
                conn.readTimeout = 20_000
                conn.requestMethod = method
                conn.setRequestProperty("Authorization", "Bearer $token")
                if (requestId != null) conn.setRequestProperty("X-HAKIM-Request-ID", requestId)
                if (body != null) {
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                conn.disconnect()
                val result = runCatching { JSONObject(text) }.getOrElse { JSONObject().put("raw", text) }
                result.put("ok", code in 200..299)
            } catch (e: Exception) {
                JSONObject().put("ok", false).put("error", e.javaClass.simpleName)
            }
        }

        private fun sendResult(resultUrl: String, requestId: String, status: String, result: JSONObject) {
            try {
                val payload = JSONObject()
                    .put("request_id", requestId)
                    .put("status", status)
                    .put("received_at_ms", System.currentTimeMillis())
                    .put("result", result)
                val conn = URL(resultUrl).openConnection() as HttpURLConnection
                conn.connectTimeout = 10_000
                conn.readTimeout = 20_000
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                runCatching { conn.inputStream.close() }
                conn.disconnect()
            } catch (_: Exception) {}
        }

        private fun ensureApprovalChannel(context: Context) {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = context.getSystemService(NotificationManager::class.java)
                nm.createNotificationChannel(NotificationChannel(APPROVAL_CHANNEL, "موافقات حكيم البعيدة", NotificationManager.IMPORTANCE_HIGH))
            }
        }
    }
}

class RemoteApprovalReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra("request_id") ?: return
        when (intent.action) {
            "org.hakim.omega.companion.REMOTE_APPROVE" -> HakimRemoteRelay.handleApproval(context, requestId, true)
            "org.hakim.omega.companion.REMOTE_REJECT" -> HakimRemoteRelay.handleApproval(context, requestId, false)
        }
    }
}
