package org.hakim.omega.companion

import android.content.Context
import android.net.Uri
import java.security.MessageDigest

/**
 * سجل أدلة خصوصي للردود المرئية داخل متصفح حكيم.
 * لا يحفظ نص الرد نفسه؛ يحفظ بصمة وطولًا ومنصة وزمنًا فقط.
 * الرصد يثبت مرور الرد عبر المراقب المحلي ولا يثبت صحة محتواه دلاليًا.
 */
object HakimAiResponseEvidence {
    const val VERSION = "1.0.0"

    fun observe(context: Context, text: String?, pageUrl: String?): Boolean {
        val body = text.orEmpty().trim()
        if (body.isBlank() || body.length > 500_000 || !HakimAiGovernance.isSupportedUrl(pageUrl)) return false
        val hash = sha256(body)
        val prefs = context.getSharedPreferences("hakim_ai_response_evidence", Context.MODE_PRIVATE)
        if (prefs.getString("last_response_hash", null) == hash) return false
        val host = runCatching { Uri.parse(pageUrl.orEmpty()).host.orEmpty().lowercase() }.getOrDefault("")
        prefs.edit()
            .putString("last_response_hash", hash)
            .putInt("last_response_length", body.length)
            .putString("last_response_host", host)
            .putLong("last_response_at", System.currentTimeMillis())
            .putLong("observed_responses", prefs.getLong("observed_responses", 0L) + 1L)
            .apply()
        return true
    }

    fun status(context: Context): String {
        val prefs = context.getSharedPreferences("hakim_ai_response_evidence", Context.MODE_PRIVATE)
        val count = prefs.getLong("observed_responses", 0L)
        val host = prefs.getString("last_response_host", null) ?: "لا يوجد"
        val length = prefs.getInt("last_response_length", 0)
        return "رصد الردود: محلي v$VERSION — المرصود: $count — آخر منصة: $host — طول آخر رد: $length — لا يُحفظ نص الرد"
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
