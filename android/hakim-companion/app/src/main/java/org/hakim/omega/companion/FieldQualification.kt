package org.hakim.omega.companion

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * تأهيل ذاتي غير مخرّب لحكيم على الهاتف الحقيقي.
 *
 * هذه الطبقة مستقلة عمدًا عن تنفيذ HakimDirectRelay في التشفير كي تعمل كفاحص
 * تبادلي للبروتوكول. النجاح هنا يثبت جولة التحكم الأساسية فقط، ولا يرفع
 * field_verified قبل اختبارات الشاشة المغلقة/إعادة التشغيل/التوافق المالي.
 */
object FieldQualification {
    private const val PREFS = "hakim"
    private const val KEY_REPORT = "field_qualification_last_report"
    private const val KEY_REPORT_MS = "field_qualification_last_report_ms"
    private const val CARRIER_PREFIX = "HC1."
    private const val CARRIER_AAD = "HAKIM-CARRIER-v1"
    private const val RESULT_PREFIX = "HR1."
    private const val RESULT_AAD = "HAKIM-RESULT-v1"
    private const val GCM_NONCE_BYTES = 12
    private const val GCM_TAG_BITS = 128
    private val random = SecureRandom()

    fun run(context: Context, timeoutMs: Int = 35_000): JSONObject {
        val app = context.applicationContext
        val startedAt = System.currentTimeMillis()
        val report = JSONObject()
            .put("schema_version", "1.0")
            .put("started_at_ms", startedAt)
            .put("field_verified", false)
            .put("physical_phone_round_trip_scope", "CORE_REMOTE_STATUS_ONLY")

        if (FinancialSafeMode.isEnabled(app)) {
            report.put("status", "BLOCKED_FINANCIAL_SAFE_MODE")
                .put("next_gate", "EXIT_FINANCIAL_SAFE_MODE_ONLY_WHEN_USER_CHOOSES")
                .put("reason", "التأهيل لا يعطّل الوضع المالي الآمن تلقائيًا")
            return persist(app, report)
        }

        HakimForegroundService.start(app)
        val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val paired = !prefs.getString("pair_token", null).isNullOrBlank()
        val configured = HakimDirectRelay.isConfigured(app)
        val relayKey = prefs.getString(HakimDirectRelay.KEY_RELAY_KEY, null)

        val local = localChecks(app, timeoutMs.coerceAtMost(6_000))
        val crypto = if (relayKey.isNullOrBlank()) {
            JSONObject().put("status", "NOT_READY").put("reason", "relay_key_missing")
        } else {
            cryptoSelfTest(relayKey)
        }
        val roundTrip = if (paired && configured && !relayKey.isNullOrBlank()) {
            encryptedStatusRoundTrip(app, timeoutMs)
        } else {
            JSONObject().put("status", "NOT_READY").put("reason", "pair_or_direct_relay_missing")
        }

        val checks = JSONObject()
            .put("local", local)
            .put("crypto", crypto)
            .put("encrypted_status_round_trip", roundTrip)
        val corePass = local.optBoolean("loopback_status_ok", false) &&
            crypto.optString("status") == "PASS" &&
            roundTrip.optString("status") == "PASS"

        report.put("checks", checks)
            .put("completed_at_ms", System.currentTimeMillis())
            .put("status", when {
                corePass -> "CORE_REMOTE_ROUND_TRIP_PASS"
                paired && configured -> "PARTIAL"
                else -> "BLOCKED_SETUP"
            })
            .put(
                "next_gate",
                if (corePass) "SCREEN_OFF_REBOOT_FINANCIAL_COMPATIBILITY"
                else "PAIR_AND_DIRECT_RELAY_THEN_RETRY",
            )
            .put(
                "qualification_rule",
                "نجاح الجولة الأساسية لا يساوي FIELD_VERIFIED؛ يلزم اجتياز المصفوفة الفيزيائية المتبقية على الجهاز الحقيقي",
            )
        return persist(app, report)
    }

    fun lastSummary(context: Context): String {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_REPORT, null)
            ?: return "التأهيل الذاتي: لم يُشغّل بعد"
        val report = runCatching { JSONObject(raw) }.getOrNull()
            ?: return "التأهيل الذاتي: التقرير السابق غير صالح"
        val status = report.optString("status", "UNKNOWN")
        val roundTrip = report.optJSONObject("checks")
            ?.optJSONObject("encrypted_status_round_trip")
            ?.optString("status", "لم يُختبر") ?: "لم يُختبر"
        return "التأهيل الذاتي: $status\n" +
            "الجولة المشفّرة: $roundTrip\n" +
            "الاعتماد الميداني الكامل: غير مكتمل حتى اختبارات الشاشة المغلقة/إعادة التشغيل/التوافق المالي"
    }

    private fun persist(context: Context, report: JSONObject): JSONObject {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_REPORT, report.toString())
            .putLong(KEY_REPORT_MS, System.currentTimeMillis())
            .apply()
        return report
    }

    private fun localChecks(context: Context, timeoutMs: Int): JSONObject {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val token = prefs.getString("pair_token", null)
        val result = JSONObject()
            .put("paired", !token.isNullOrBlank())
            .put("direct_relay_configured", HakimDirectRelay.isConfigured(context))
            .put("foreground_service_running", HakimForegroundService.running)
            .put("accessibility_connected", HakimAccessibilityService.instance != null)
            .put("notification_listener_connected", HakimNotificationListener.isConnected())
            .put("financial_safe_mode", FinancialSafeMode.isEnabled(context))

        if (token.isNullOrBlank()) return result.put("loopback_status_ok", false).put("loopback_error", "not_paired")
        val deadline = System.currentTimeMillis() + timeoutMs.coerceAtLeast(1_000)
        var lastError = "loopback_not_ready"
        while (System.currentTimeMillis() < deadline) {
            try {
                val conn = URL("http://127.0.0.1:${LocalControlServer.PORT}/v1/status").openConnection() as HttpURLConnection
                conn.connectTimeout = 1_000
                conn.readTimeout = 2_000
                conn.requestMethod = "GET"
                conn.setRequestProperty("Authorization", "Bearer $token")
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                conn.disconnect()
                if (code in 200..299) {
                    return result.put("loopback_status_ok", true)
                        .put("status_payload", runCatching { JSONObject(text) }.getOrElse { JSONObject().put("raw", text.take(300)) })
                }
                lastError = "http_$code"
            } catch (e: Exception) {
                lastError = e.javaClass.simpleName
            }
            Thread.sleep(250)
        }
        return result.put("loopback_status_ok", false).put("loopback_error", lastError)
    }

    private fun cryptoSelfTest(relayKey: String): JSONObject {
        return try {
            val requestId = "field.crypto.${System.currentTimeMillis()}"
            val expiresAt = System.currentTimeMillis() + 60_000
            val payloadB64 = ""
            val signature = sign(relayKey, requestId, "status", expiresAt, payloadB64)
            val validHmac = verifySignature(relayKey, requestId, "status", expiresAt, payloadB64, signature)
            val badSignature = (if (signature.first() == '0') "1" else "0") + signature.drop(1)
            val rejectsBadHmac = !verifySignature(relayKey, requestId, "status", expiresAt, payloadB64, badSignature)

            val raw = JSONObject()
                .put("request_id", requestId)
                .put("op", "status")
                .put("expires_at_ms", expiresAt)
                .put("payload_b64", payloadB64)
                .put("signature", signature)
                .toString()
            val carrier = encrypt(CARRIER_PREFIX, CARRIER_AAD, raw, relayKey)
            val decryptsValidCarrier = decrypt(CARRIER_PREFIX, CARRIER_AAD, carrier, relayKey) == raw
            val rejectsPlaintext = decrypt(CARRIER_PREFIX, CARRIER_AAD, raw, relayKey) == null

            val packed = Base64.decode(
                carrier.removePrefix(CARRIER_PREFIX),
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
            )
            packed[packed.lastIndex] = (packed.last().toInt() xor 0x01).toByte()
            val tampered = CARRIER_PREFIX + Base64.encodeToString(
                packed,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
            )
            val rejectsBadGcmTag = decrypt(CARRIER_PREFIX, CARRIER_AAD, tampered, relayKey) == null
            val pass = validHmac && rejectsBadHmac && decryptsValidCarrier && rejectsPlaintext && rejectsBadGcmTag
            JSONObject()
                .put("status", if (pass) "PASS" else "FAIL")
                .put("valid_hmac", validHmac)
                .put("rejects_bad_hmac", rejectsBadHmac)
                .put("valid_hc1_round_trip", decryptsValidCarrier)
                .put("rejects_plaintext_carrier", rejectsPlaintext)
                .put("rejects_bad_gcm_tag", rejectsBadGcmTag)
        } catch (e: Exception) {
            JSONObject().put("status", "FAIL").put("error", e.javaClass.simpleName)
        }
    }

    private fun encryptedStatusRoundTrip(context: Context, timeoutMs: Int): JSONObject {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val topic = prefs.getString(HakimDirectRelay.KEY_TOPIC, null)
        val resultTopic = prefs.getString(HakimDirectRelay.KEY_RESULT_TOPIC, null)
        val relayKey = prefs.getString(HakimDirectRelay.KEY_RELAY_KEY, null)
        val relayBase = prefs.getString(HakimDirectRelay.KEY_RELAY_BASE, "https://ntfy.sh")
            ?.trim()?.removeSuffix("/") ?: "https://ntfy.sh"
        if (topic.isNullOrBlank() || resultTopic.isNullOrBlank() || relayKey.isNullOrBlank()) {
            return JSONObject().put("status", "NOT_READY").put("reason", "relay_configuration_incomplete")
        }

        return try {
            // أعط الخدمة مهلة قصيرة لبدء مستمع القناة بعد تشغيلها من الواجهة.
            Thread.sleep(1_000)
            val requestId = "field.${System.currentTimeMillis()}.${randomHex(6)}"
            val expiresAt = System.currentTimeMillis() + timeoutMs + 20_000L
            val payloadB64 = ""
            val signature = sign(relayKey, requestId, "status", expiresAt, payloadB64)
            val envelope = JSONObject()
                .put("request_id", requestId)
                .put("op", "status")
                .put("expires_at_ms", expiresAt)
                .put("payload_b64", payloadB64)
                .put("signature", signature)
                .toString()
            val carrier = encrypt(CARRIER_PREFIX, CARRIER_AAD, envelope, relayKey)
            val postCode = postText("$relayBase/$topic", carrier)
            if (postCode !in 200..299) {
                return JSONObject().put("status", "FAIL").put("stage", "publish_command").put("http_code", postCode)
            }

            val conn = URL("$relayBase/$resultTopic/json?since=10m").openConnection() as HttpURLConnection
            conn.connectTimeout = 10_000
            conn.readTimeout = timeoutMs.coerceAtLeast(10_000)
            conn.requestMethod = "GET"
            conn.setRequestProperty("Accept", "application/x-ndjson")
            val code = conn.responseCode
            if (code !in 200..299) {
                conn.disconnect()
                return JSONObject().put("status", "FAIL").put("stage", "listen_result").put("http_code", code)
            }

            val deadline = System.currentTimeMillis() + timeoutMs
            BufferedReader(InputStreamReader(conn.inputStream, Charsets.UTF_8)).use { reader ->
                while (System.currentTimeMillis() < deadline) {
                    val line = reader.readLine() ?: break
                    val event = runCatching { JSONObject(line) }.getOrNull() ?: continue
                    if (event.optString("event") != "message") continue
                    val resultCarrier = event.optString("message").trim()
                    val raw = decrypt(RESULT_PREFIX, RESULT_AAD, resultCarrier, relayKey) ?: continue
                    val resultEnvelope = runCatching { JSONObject(raw) }.getOrNull() ?: continue
                    if (resultEnvelope.optString("request_id") != requestId) continue
                    conn.disconnect()
                    val result = resultEnvelope.optJSONObject("result") ?: JSONObject()
                    val pass = resultEnvelope.optString("status") == "ok" && result.optBoolean("ok", false)
                    return JSONObject()
                        .put("status", if (pass) "PASS" else "FAIL")
                        .put("request_id", requestId)
                        .put("command_publish_http", postCode)
                        .put("result_status", resultEnvelope.optString("status"))
                        .put("loopback_result_ok", result.optBoolean("ok", false))
                        .put("hc1_command", true)
                        .put("hr1_result", true)
                }
            }
            conn.disconnect()
            JSONObject().put("status", "FAIL").put("stage", "result_timeout").put("request_id", requestId)
        } catch (e: Exception) {
            JSONObject().put("status", "FAIL")
                .put("stage", "exception")
                .put("error", e.javaClass.simpleName)
                .put("detail", (e.message ?: "").take(180))
        }
    }

    private fun postText(url: String, body: String): Int {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 15_000
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "text/plain; charset=utf-8")
        conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = conn.responseCode
        runCatching { (if (code in 200..299) conn.inputStream else conn.errorStream)?.close() }
        conn.disconnect()
        return code
    }

    private fun sign(relayKey: String, requestId: String, op: String, expiresAt: Long, payloadB64: String): String {
        val canonical = "$requestId\n$op\n$expiresAt\n$payloadB64"
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(relayKey.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(canonical.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun verifySignature(relayKey: String, requestId: String, op: String, expiresAt: Long, payloadB64: String, signature: String): Boolean {
        val expected = sign(relayKey, requestId, op, expiresAt, payloadB64)
        return MessageDigest.isEqual(
            expected.toByteArray(Charsets.US_ASCII),
            signature.lowercase().toByteArray(Charsets.US_ASCII),
        )
    }

    private fun encrypt(prefix: String, aad: String, raw: String, relayKey: String): String {
        val nonce = ByteArray(GCM_NONCE_BYTES).also { random.nextBytes(it) }
        val keyMaterial = "$aad\u0000$relayKey".toByteArray(Charsets.UTF_8)
        val aesKey = MessageDigest.getInstance("SHA-256").digest(keyMaterial)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(aesKey, "AES"), GCMParameterSpec(GCM_TAG_BITS, nonce))
        cipher.updateAAD(aad.toByteArray(Charsets.UTF_8))
        val packed = nonce + cipher.doFinal(raw.toByteArray(Charsets.UTF_8))
        return prefix + Base64.encodeToString(packed, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }

    private fun decrypt(prefix: String, aad: String, carrier: String, relayKey: String): String? {
        if (!carrier.startsWith(prefix)) return null
        val packed = runCatching {
            Base64.decode(carrier.removePrefix(prefix), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        }.getOrNull() ?: return null
        if (packed.size < GCM_NONCE_BYTES + 16) return null
        val nonce = packed.copyOfRange(0, GCM_NONCE_BYTES)
        val ciphertext = packed.copyOfRange(GCM_NONCE_BYTES, packed.size)
        return runCatching {
            val keyMaterial = "$aad\u0000$relayKey".toByteArray(Charsets.UTF_8)
            val aesKey = MessageDigest.getInstance("SHA-256").digest(keyMaterial)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(aesKey, "AES"), GCMParameterSpec(GCM_TAG_BITS, nonce))
            cipher.updateAAD(aad.toByteArray(Charsets.UTF_8))
            String(cipher.doFinal(ciphertext), Charsets.UTF_8)
        }.getOrNull()
    }

    private fun randomHex(bytes: Int): String = ByteArray(bytes).also { random.nextBytes(it) }
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
