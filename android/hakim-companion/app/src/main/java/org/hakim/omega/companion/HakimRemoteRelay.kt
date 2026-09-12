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
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Outbound-only remote transport for HAKIM Companion.
 *
 * Security invariants:
 * - never opens a non-loopback listener;
 * - public carrier messages are ciphertext-only (HC1 / AES-256-GCM);
 * - every decrypted remote command is authenticated again with HMAC-SHA256;
 * - remote state-changing operations require an explicit Android approval;
 * - request ids are claimed before execution to prevent replay;
 * - expired requests fail closed;
 * - the existing pair token remains local and is only used against 127.0.0.1.
 *
 * Reliability:
 * - uses cached polling with a persisted message-id cursor;
 * - replays a short cache window on first start so transient mobile disconnects
 *   cannot silently lose commands;
 * - exposes last successful poll / last transport error in app preferences.
 *
 * Independence:
 * - no Make, no paid API, no account-bound relay is required;
 * - command and result topics are both encrypted end-to-end;
 * - the relay base URL is configurable and defaults to the free ntfy.sh service.
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
            val resultTopic = prefs.getString(KEY_RESULT_TOPIC, null)
            val relayBase = prefs.getString(KEY_RELAY_BASE, DEFAULT_RELAY_BASE) ?: DEFAULT_RELAY_BASE
            val relayKey = prefs.getString(KEY_RELAY_KEY, null)
            if (topic.isNullOrBlank() || resultTopic.isNullOrBlank() || relayKey.isNullOrBlank() || !validRelayBase(relayBase)) {
                prefs.edit().putString(KEY_LAST_ERROR, "relay_not_configured").apply()
                sleep(5_000L)
                continue
            }

            val cursor = prefs.getString(KEY_LAST_NTFY_ID, null)
            val since = if (cursor.isNullOrBlank()) {
                INITIAL_REPLAY_WINDOW
            } else {
                URLEncoder.encode(cursor, Charsets.UTF_8.name())
            }

            try {
                val url = URL("$relayBase/$topic/json?poll=1&since=$since")
                val conn = url.openConnection() as HttpURLConnection
                conn.connectTimeout = 15_000
                conn.readTimeout = 25_000
                conn.requestMethod = "GET"
                conn.setRequestProperty("Accept", "application/x-ndjson")

                val code = conn.responseCode
                if (code !in 200..299) {
                    val body = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                    conn.disconnect()
                    throw IllegalStateException("relay_http_$code:${body.take(120)}")
                }

                val lines = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readLines() }
                conn.disconnect()

                var newestMessageId = cursor
                for (line in lines) {
                    if (!running.get()) break
                    val event = runCatching { JSONObject(line) }.getOrNull() ?: continue
                    if (event.optString("event") != "message") continue
                    val id = event.optString("id").trim()
                    if (!cursor.isNullOrBlank() && id == cursor) continue
                    handleNtfyEvent(event, resultTopic, relayBase, relayKey)
                    if (id.isNotBlank()) newestMessageId = id
                }

                val editor = prefs.edit()
                    .putLong(KEY_LAST_POLL_MS, System.currentTimeMillis())
                    .remove(KEY_LAST_ERROR)
                if (!newestMessageId.isNullOrBlank() && newestMessageId != cursor) {
                    editor.putString(KEY_LAST_NTFY_ID, newestMessageId)
                }
                editor.apply()

                retryMs = 2_000L
                sleep(POLL_INTERVAL_MS)
            } catch (e: Exception) {
                prefs.edit()
                    .putString(KEY_LAST_ERROR, e.javaClass.simpleName + ":" + (e.message ?: ""))
                    .apply()
                sleep(retryMs)
                retryMs = (retryMs * 2).coerceAtMost(60_000L)
            }
        }
    }

    private fun handleNtfyEvent(event: JSONObject, resultTopic: String, relayBase: String, relayKey: String) {
        val carrier = event.optString("message").trim()
        if (carrier.length !in 32..65536) return
        val raw = decryptCarrier(carrier, relayKey) ?: return
        val envelope = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val requestId = envelope.optString("request_id")
        val op = envelope.optString("op")
        val expiresAt = envelope.optLong("expires_at_ms", 0L)
        val payloadB64 = envelope.optString("payload_b64")
        val signature = envelope.optString("signature")

        if (!REQUEST_ID.matches(requestId) || !ALLOWED_OPS.contains(op)) return
        if (payloadB64.length > 32768 || !SIGNATURE.matches(signature)) return
        if (!validSignature(relayKey, requestId, op, expiresAt, payloadB64, signature)) return
        if (expiresAt <= System.currentTimeMillis()) {
            sendResult(context, resultTopic, relayBase, relayKey, requestId, "expired", JSONObject().put("error", "request_expired"))
            return
        }
        if (!claimRemoteRequest(context, requestId)) {
            sendResult(context, resultTopic, relayBase, relayKey, requestId, "duplicate", JSONObject().put("error", "duplicate_request"))
            return
        }
        if (READ_ONLY_OPS.contains(op)) {
            val result = executeEnvelope(context, envelope)
            sendResult(context, resultTopic, relayBase, relayKey, requestId, if (result.optBoolean("ok", false)) "ok" else "error", result)
        } else {
            savePending(context, envelope, resultTopic, relayBase, relayKey)
            showApproval(context, requestId, op)
        }
    }

    private fun sleep(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }

    companion object {
        const val PREFS = "hakim"
        const val KEY_TOPIC = "relay_topic"
        const val KEY_RESULT_TOPIC = "relay_result_topic"
        const val KEY_RELAY_BASE = "relay_base_url"
        const val KEY_RELAY_KEY = "relay_hmac_key"
        const val KEY_LAST_NTFY_ID = "relay_last_ntfy_id"
        const val KEY_LAST_POLL_MS = "relay_last_poll_ms"
        const val KEY_LAST_ERROR = "relay_last_error"
        const val KEY_LAST_RESULT_ERROR = "relay_last_result_error"
        const val KEY_LAST_RESULT_SEND_MS = "relay_last_result_send_ms"
        private const val POLL_INTERVAL_MS = 2_500L
        private const val INITIAL_REPLAY_WINDOW = "10m"
        private const val APPROVAL_CHANNEL = "hakim_remote_approval"
        private const val ACTION_APPROVE = "org.hakim.omega.companion.REMOTE_APPROVE"
        private const val ACTION_REJECT = "org.hakim.omega.companion.REMOTE_REJECT"
        private const val EXTRA_REQUEST_ID = "request_id"
        private const val CARRIER_PREFIX = "HC1."
        private const val CARRIER_AAD = "HAKIM-CARRIER-v1"
        private const val RESULT_PREFIX = "HR1."
        private const val RESULT_AAD = "HAKIM-RESULT-v1"
        private const val DEFAULT_RELAY_BASE = "https://ntfy.sh"
        private const val GCM_NONCE_BYTES = 12
        private const val GCM_TAG_BITS = 128
        private val REQUEST_ID = Regex("^[A-Za-z0-9._:-]{8,128}$")
        private val SIGNATURE = Regex("^[0-9a-fA-F]{64}$")
        private val RELAY_KEY = Regex("^[A-Za-z0-9_-]{40,100}$")
        private val READ_ONLY_OPS = setOf("status", "ui", "notifications", "screenshot")
        private val ALLOWED_OPS = READ_ONLY_OPS + setOf("action", "launch")

        fun configure(
            context: Context,
            topic: String?,
            resultTopic: String?,
            relayKey: String?,
            relayBase: String? = DEFAULT_RELAY_BASE,
        ) {
            val base = relayBase?.trim()?.removeSuffix("/") ?: DEFAULT_RELAY_BASE
            if (topic.isNullOrBlank() || !Regex("^[A-Za-z0-9_-]{20,120}$").matches(topic)) return
            if (resultTopic.isNullOrBlank() || !Regex("^[A-Za-z0-9_-]{20,120}$").matches(resultTopic)) return
            if (relayKey.isNullOrBlank() || !RELAY_KEY.matches(relayKey)) return
            if (!validRelayBase(base)) return
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_TOPIC, topic)
                .putString(KEY_RESULT_TOPIC, resultTopic)
                .putString(KEY_RELAY_BASE, base)
                .putString(KEY_RELAY_KEY, relayKey)
                .remove(KEY_LAST_ERROR)
                .remove(KEY_LAST_NTFY_ID)
                .apply()
        }

        private fun validRelayBase(value: String): Boolean =
            Regex("^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%-]+)*$").matches(value)

        private fun decryptCarrier(carrier: String, relayKey: String): String? {
            if (!carrier.startsWith(CARRIER_PREFIX)) return null
            val packed = runCatching {
                Base64.decode(
                    carrier.removePrefix(CARRIER_PREFIX),
                    Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
                )
            }.getOrNull() ?: return null
            if (packed.size < GCM_NONCE_BYTES + 16) return null
            val nonce = packed.copyOfRange(0, GCM_NONCE_BYTES)
            val ciphertext = packed.copyOfRange(GCM_NONCE_BYTES, packed.size)
            return runCatching {
                val keyMaterial = "$CARRIER_AAD\u0000$relayKey".toByteArray(Charsets.UTF_8)
                val aesKey = MessageDigest.getInstance("SHA-256").digest(keyMaterial)
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(
                    Cipher.DECRYPT_MODE,
                    SecretKeySpec(aesKey, "AES"),
                    GCMParameterSpec(GCM_TAG_BITS, nonce),
                )
                cipher.updateAAD(CARRIER_AAD.toByteArray(Charsets.UTF_8))
                String(cipher.doFinal(ciphertext), Charsets.UTF_8)
            }.getOrNull()
        }

        private fun validSignature(
            relayKey: String,
            requestId: String,
            op: String,
            expiresAt: Long,
            payloadB64: String,
            signature: String,
        ): Boolean {
            val canonical = "$requestId\n$op\n$expiresAt\n$payloadB64"
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(relayKey.toByteArray(Charsets.UTF_8), "HmacSHA256"))
            val expected = mac.doFinal(canonical.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it.toInt() and 0xff) }
            return MessageDigest.isEqual(
                expected.toByteArray(Charsets.US_ASCII),
                signature.lowercase().toByteArray(Charsets.US_ASCII),
            )
        }

        private fun claimRemoteRequest(context: Context, requestId: String): Boolean {
            val prefs = context.getSharedPreferences("hakim_remote_idempotency", Context.MODE_PRIVATE)
            if (prefs.contains(requestId)) return false
            return prefs.edit().putLong(requestId, System.currentTimeMillis()).commit()
        }

        private fun savePending(
            context: Context,
            envelope: JSONObject,
            resultTopic: String,
            relayBase: String,
            relayKey: String,
        ) {
            val id = envelope.optString("request_id")
            context.getSharedPreferences("hakim_remote_pending", Context.MODE_PRIVATE).edit()
                .putString("$id.envelope", envelope.toString())
                .putString("$id.result_topic", resultTopic)
                .putString("$id.relay_base", relayBase)
                .putString("$id.relay_key", relayKey)
                .apply()
        }

        private data class PendingRemote(
            val envelope: JSONObject,
            val resultTopic: String,
            val relayBase: String,
            val relayKey: String,
        )

        private fun takePending(context: Context, requestId: String): PendingRemote? {
            val prefs = context.getSharedPreferences("hakim_remote_pending", Context.MODE_PRIVATE)
            val raw = prefs.getString("$requestId.envelope", null) ?: return null
            val topic = prefs.getString("$requestId.result_topic", null) ?: return null
            val base = prefs.getString("$requestId.relay_base", null) ?: return null
            val key = prefs.getString("$requestId.relay_key", null) ?: return null
            prefs.edit()
                .remove("$requestId.envelope")
                .remove("$requestId.result_topic")
                .remove("$requestId.relay_base")
                .remove("$requestId.relay_key")
                .apply()
            return runCatching { PendingRemote(JSONObject(raw), topic, base, key) }.getOrNull()
        }

        private fun showApproval(context: Context, requestId: String, op: String) {
            ensureApprovalChannel(context)
            val approve = PendingIntent.getBroadcast(
                context,
                requestId.hashCode(),
                Intent(context, RemoteApprovalReceiver::class.java)
                    .setAction(ACTION_APPROVE)
                    .putExtra(EXTRA_REQUEST_ID, requestId),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val reject = PendingIntent.getBroadcast(
                context,
                requestId.hashCode() xor 0x55AA,
                Intent(context, RemoteApprovalReceiver::class.java)
                    .setAction(ACTION_REJECT)
                    .putExtra(EXTRA_REQUEST_ID, requestId),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val notification = android.app.Notification.Builder(context, APPROVAL_CHANNEL)
                .setContentTitle("حكيم — موافقة مطلوبة")
                .setContentText("طلب تحكم على الهاتف: $op")
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setAutoCancel(true)
                .addAction(android.R.drawable.ic_input_add, "موافقة", approve)
                .addAction(android.R.drawable.ic_delete, "رفض", reject)
                .build()
            context.getSystemService(NotificationManager::class.java)
                .notify(requestId.hashCode(), notification)
        }

        fun handleApproval(context: Context, requestId: String, approved: Boolean) {
            val pending = takePending(context, requestId) ?: return
            val envelope = pending.envelope
            if (!approved) {
                sendResult(
                    context,
                    pending.resultTopic,
                    pending.relayBase,
                    pending.relayKey,
                    requestId,
                    "rejected",
                    JSONObject().put("ok", false).put("error", "rejected_by_user"),
                )
                return
            }
            val expiresAt = envelope.optLong("expires_at_ms", 0L)
            if (expiresAt <= System.currentTimeMillis()) {
                sendResult(
                    context,
                    pending.resultTopic,
                    pending.relayBase,
                    pending.relayKey,
                    requestId,
                    "expired",
                    JSONObject().put("ok", false).put("error", "request_expired"),
                )
                return
            }
            Executors.newSingleThreadExecutor().execute {
                val result = executeEnvelope(context, envelope)
                sendResult(
                    context,
                    pending.resultTopic,
                    pending.relayBase,
                    pending.relayKey,
                    requestId,
                    if (result.optBoolean("ok", false)) "ok" else "error",
                    result,
                )
            }
        }

        private fun decodePayload(envelope: JSONObject): JSONObject {
            val payloadB64 = envelope.optString("payload_b64")
            if (payloadB64.isBlank()) return JSONObject()
            return runCatching {
                val raw = String(
                    Base64.decode(
                        payloadB64,
                        Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
                    ),
                    Charsets.UTF_8,
                )
                JSONObject(raw)
            }.getOrElse { JSONObject() }
        }

        private fun executeEnvelope(context: Context, envelope: JSONObject): JSONObject {
            val requestId = envelope.optString("request_id")
            val op = envelope.optString("op")
            val payload = decodePayload(envelope)
            return when (op) {
                "status" -> localRequest(context, "GET", "/v1/status", null, null)
                "ui" -> localRequest(context, "GET", "/v1/ui", null, null)
                "notifications" -> localRequest(context, "GET", "/v1/notifications", null, null)
                "screenshot" -> localRequest(context, "GET", "/v1/screenshot", null, null)
                "action" -> localRequest(context, "POST", "/v1/action", payload, requestId)
                "launch" -> localRequest(context, "POST", "/v1/launch", payload, requestId)
                else -> JSONObject().put("ok", false).put("error", "unsupported_operation")
            }
        }

        private fun localRequest(
            context: Context,
            method: String,
            path: String,
            body: JSONObject?,
            requestId: String?,
        ): JSONObject {
            val token = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString("pair_token", null)
                ?: return JSONObject().put("ok", false).put("error", "not_paired")
            return try {
                val conn = URL("http://127.0.0.1:${LocalControlServer.PORT}$path")
                    .openConnection() as HttpURLConnection
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
                val result = runCatching { JSONObject(text) }
                    .getOrElse { JSONObject().put("raw", text) }
                result.put("ok", code in 200..299)
            } catch (e: Exception) {
                JSONObject().put("ok", false).put("error", e.javaClass.simpleName)
            }
        }

        private fun sendResult(
            context: Context,
            resultTopic: String,
            relayBase: String,
            relayKey: String,
            requestId: String,
            status: String,
            result: JSONObject,
        ) {
            try {
                val payload = JSONObject()
                    .put("request_id", requestId)
                    .put("status", status)
                    .put("received_at_ms", System.currentTimeMillis())
                    .put("result", result)
                    .toString()
                val carrier = encryptResult(payload, relayKey)
                val conn = URL("$relayBase/$resultTopic").openConnection() as HttpURLConnection
                conn.connectTimeout = 10_000
                conn.readTimeout = 20_000
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "text/plain; charset=utf-8")
                conn.outputStream.use { it.write(carrier.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                if (code !in 200..299) {
                    conn.errorStream?.close()
                    throw IllegalStateException("result_transport_http_$code")
                }
                runCatching { conn.inputStream.close() }
                conn.disconnect()
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putLong(KEY_LAST_RESULT_SEND_MS, System.currentTimeMillis())
                    .remove(KEY_LAST_RESULT_ERROR)
                    .apply()
            } catch (e: Exception) {
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString(KEY_LAST_RESULT_ERROR, e.javaClass.simpleName + ":" + (e.message ?: ""))
                    .apply()
            }
        }

        private fun encryptResult(raw: String, relayKey: String): String {
            val nonce = ByteArray(GCM_NONCE_BYTES).also { SecureRandom().nextBytes(it) }
            val keyMaterial = "$RESULT_AAD\u0000$relayKey".toByteArray(Charsets.UTF_8)
            val aesKey = MessageDigest.getInstance("SHA-256").digest(keyMaterial)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.ENCRYPT_MODE,
                SecretKeySpec(aesKey, "AES"),
                GCMParameterSpec(GCM_TAG_BITS, nonce),
            )
            cipher.updateAAD(RESULT_AAD.toByteArray(Charsets.UTF_8))
            val ciphertext = cipher.doFinal(raw.toByteArray(Charsets.UTF_8))
            val packed = nonce + ciphertext
            return RESULT_PREFIX + Base64.encodeToString(
                packed,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
            )
        }

        private fun ensureApprovalChannel(context: Context) {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = context.getSystemService(NotificationManager::class.java)
                nm.createNotificationChannel(
                    NotificationChannel(
                        APPROVAL_CHANNEL,
                        "موافقات حكيم البعيدة",
                        NotificationManager.IMPORTANCE_HIGH,
                    ),
                )
            }
        }
    }
}

class RemoteApprovalReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra("request_id") ?: return
        when (intent.action) {
            "org.hakim.omega.companion.REMOTE_APPROVE" ->
                HakimRemoteRelay.handleApproval(context, requestId, true)
            "org.hakim.omega.companion.REMOTE_REJECT" ->
                HakimRemoteRelay.handleApproval(context, requestId, false)
        }
    }
}
