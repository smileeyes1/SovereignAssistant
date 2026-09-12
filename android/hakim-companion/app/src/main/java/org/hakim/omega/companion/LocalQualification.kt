package org.hakim.omega.companion

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * تأهيل محلي حتمي لحكيم بلا ناقل خارجي ولا API ولا صلاحية جهاز عامة.
 * يختبر: الاقتران، loopback الموثق، متصفح حكيم المملوك، DOM، واللقطة.
 * لا يرفع أبدًا ادعاء FIELD_VERIFIED؛ اختبار الهاتف الميداني الكامل يبقى بوابة مستقلة.
 */
object LocalQualification {
    private const val PREFS = "hakim"
    private const val KEY_REPORT = "local_qualification_report"
    private const val PROOF_VALUE = "حكيم-محلي-مؤهل"

    fun run(context: Context): JSONObject {
        val started = System.currentTimeMillis()
        val report = JSONObject()
            .put("mode", "SOVEREIGN_LOCAL")
            .put("started_at_ms", started)
            .put("field_verified", false)
            .put("external_transport", false)

        if (FinancialSafeMode.isEnabled(context)) {
            return persist(context, report
                .put("status", "BLOCKED_FINANCIAL_SAFE_MODE")
                .put("ok", false)
                .put("next_gate", "EXIT_FINANCIAL_SAFE_MODE_LOCALLY"))
        }

        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val token = prefs.getString("pair_token", null)
        if (token.isNullOrBlank()) {
            return persist(context, report
                .put("status", "UNPAIRED")
                .put("ok", false)
                .put("next_gate", "LOCAL_PAIRING_REQUIRED"))
        }

        HakimForegroundService.start(context)
        val status = awaitLoopbackStatus(token)
        val loopbackPass = status?.optBoolean("loopback_only", false) == true &&
            status.optBoolean("control_server_listening", false) &&
            status.optBoolean("external_transport_enabled", true) == false

        val browserAttached = HakimBrowserController.isAttached()
        val proofLoaded = browserAttached && HakimBrowserController.action(JSONObject().put("action", "local_proof"))
        if (proofLoaded) Thread.sleep(350L)
        val textSet = proofLoaded && HakimBrowserController.action(JSONObject()
            .put("action", "set_text")
            .put("id", "hakim-proof-input")
            .put("value", PROOF_VALUE))
        val clicked = proofLoaded && HakimBrowserController.action(JSONObject()
            .put("action", "click_css")
            .put("selector", "#hakim-proof-button"))
        val nodes = if (proofLoaded) HakimBrowserController.uiSnapshot() else org.json.JSONArray()
        var hasInput = false
        var hasButton = false
        for (i in 0 until nodes.length()) {
            when (nodes.optJSONObject(i)?.optString("id")) {
                "hakim-proof-input" -> hasInput = true
                "hakim-proof-button" -> hasButton = true
            }
        }
        val screenshot = if (proofLoaded) HakimBrowserController.screenshotBase64() else null
        val screenshotPass = screenshot?.let {
            runCatching {
                val bytes = Base64.decode(it, Base64.DEFAULT)
                bytes.size > 8 && bytes[0] == 0x89.toByte() && bytes[1] == 0x50.toByte() &&
                    bytes[2] == 0x4e.toByte() && bytes[3] == 0x47.toByte()
            }.getOrDefault(false)
        } ?: false

        val browserPass = browserAttached && proofLoaded && textSet && clicked && hasInput && hasButton && screenshotPass
        val ok = loopbackPass && browserPass
        return persist(context, report
            .put("status", if (ok) "LOCAL_CORE_PASS" else "LOCAL_CORE_FAIL")
            .put("ok", ok)
            .put("loopback_authenticated", loopbackPass)
            .put("owned_browser_attached", browserAttached)
            .put("local_proof_loaded", proofLoaded)
            .put("dom_text_set", textSet)
            .put("dom_click", clicked)
            .put("dom_nodes_verified", hasInput && hasButton)
            .put("browser_screenshot_png", screenshotPass)
            .put("completed_at_ms", System.currentTimeMillis())
            .put("next_gate", if (ok) "PHYSICAL_PHONE_MATRIX_STILL_REQUIRED" else "REPAIR_LOCAL_CORE"))
    }

    fun summary(context: Context): JSONObject {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_REPORT, null)
            ?: return JSONObject().put("status", "NOT_RUN").put("field_verified", false)
        val r = runCatching { JSONObject(raw) }.getOrElse {
            return JSONObject().put("status", "INVALID_LOCAL_REPORT").put("field_verified", false)
        }
        return JSONObject()
            .put("status", r.optString("status", "UNKNOWN"))
            .put("ok", r.optBoolean("ok", false))
            .put("field_verified", false)
            .put("loopback_authenticated", r.optBoolean("loopback_authenticated", false))
            .put("owned_browser_attached", r.optBoolean("owned_browser_attached", false))
            .put("dom_nodes_verified", r.optBoolean("dom_nodes_verified", false))
            .put("browser_screenshot_png", r.optBoolean("browser_screenshot_png", false))
            .put("completed_at_ms", r.optLong("completed_at_ms", 0L))
            .put("next_gate", r.optString("next_gate", "UNKNOWN"))
    }

    private fun persist(context: Context, report: JSONObject): JSONObject {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_REPORT, report.toString())
            .apply()
        return report
    }

    private fun awaitLoopbackStatus(token: String): JSONObject? {
        repeat(12) {
            val result = runCatching { localStatus(token) }.getOrNull()
            if (result != null) return result
            try { Thread.sleep(200L) } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                return null
            }
        }
        return null
    }

    private fun localStatus(token: String): JSONObject? {
        val conn = URL("http://127.0.0.1:${LocalControlServer.PORT}/v1/status").openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 1_000
            conn.readTimeout = 1_500
            conn.requestMethod = "GET"
            conn.setRequestProperty("Authorization", "Bearer $token")
            if (conn.responseCode != 200) return null
            JSONObject(conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() })
        } finally {
            conn.disconnect()
        }
    }
}
