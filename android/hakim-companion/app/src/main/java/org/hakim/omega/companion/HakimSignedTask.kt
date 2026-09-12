package org.hakim.omega.companion

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.Executors
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * قناة المهام السيادية المحلية.
 * لا تستخدم أي ناقل خارجي. المهمة تصل فقط عبر رابط hakim://task يفتحه المستخدم صراحة.
 * الخطة موقعة HMAC بمفتاح الاقتران المحلي، محدودة الصلاحية، ومحمية من الإعادة.
 */
object HakimSignedTask {
    private const val PREFS = "hakim"
    private const val AAD = "HAKIM-TASK-v1"
    private const val MAX_PLAN_CHARS = 48_000
    private const val MAX_STEPS = 40
    private const val MAX_WAIT_MS = 10_000L
    private const val MAX_FUTURE_MS = 24L * 60L * 60L * 1000L
    private val REQUEST_ID = Regex("^[A-Za-z0-9._:-]{8,128}$")
    private val SIG = Regex("^[0-9a-fA-F]{64}$")
    private val executor = Executors.newSingleThreadExecutor()

    fun accept(context: Context, uri: Uri): String {
        if (uri.scheme != "hakim" || uri.host != "task") return "ignored"
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val token = prefs.getString("pair_token", null) ?: return fail(context, "task_unpaired")
        val planB64 = uri.getQueryParameter("plan").orEmpty()
        val signature = uri.getQueryParameter("sig").orEmpty()
        if (planB64.isBlank() || planB64.length > MAX_PLAN_CHARS || !SIG.matches(signature)) {
            return fail(context, "task_invalid_envelope")
        }
        if (!validSignature(token, planB64, signature)) return fail(context, "task_bad_signature")

        val raw = runCatching {
            String(
                Base64.decode(planB64, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING),
                Charsets.UTF_8,
            )
        }.getOrNull() ?: return fail(context, "task_bad_encoding")

        val plan = runCatching { JSONObject(raw) }.getOrNull() ?: return fail(context, "task_bad_json")
        val requestId = plan.optString("request_id")
        val expiresAt = plan.optLong("expires_at_ms", 0L)
        val now = System.currentTimeMillis()
        if (!REQUEST_ID.matches(requestId)) return fail(context, "task_bad_request_id")
        if (expiresAt <= now || expiresAt - now > MAX_FUTURE_MS) return fail(context, "task_expired_or_too_far")
        val steps = plan.optJSONArray("steps") ?: return fail(context, "task_missing_steps")
        if (steps.length() !in 1..MAX_STEPS) return fail(context, "task_bad_step_count")
        if (!claim(context, requestId)) return fail(context, "task_duplicate")

        prefs.edit()
            .putString("last_signed_task", "accepted:$requestId")
            .putLong("last_signed_task_ms", now)
            .apply()

        executor.execute {
            var result = "completed:$requestId"
            for (i in 0 until steps.length()) {
                if (System.currentTimeMillis() >= expiresAt) {
                    result = "expired_during_run:$requestId:$i"
                    break
                }
                val step = steps.optJSONObject(i)
                if (step == null) {
                    result = "bad_step:$requestId:$i"
                    break
                }
                val action = step.optString("action")
                if (action == "wait") {
                    val ms = step.optLong("ms", 0L).coerceIn(0L, MAX_WAIT_MS)
                    try { Thread.sleep(ms) } catch (_: InterruptedException) { Thread.currentThread().interrupt(); result = "interrupted:$requestId:$i"; break }
                    continue
                }
                if (action !in ALLOWED_ACTIONS) {
                    result = "action_denied:$requestId:$i:$action"
                    break
                }
                val ok = HakimBrowserController.action(step)
                if (!ok) {
                    result = "step_failed:$requestId:$i:$action"
                    break
                }
            }
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString("last_signed_task", result)
                .putLong("last_signed_task_ms", System.currentTimeMillis())
                .apply()
        }
        return "accepted:$requestId"
    }

    private fun validSignature(token: String, planB64: String, signature: String): Boolean {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(token.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val expected = mac.doFinal("$AAD\n$planB64".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
        return MessageDigest.isEqual(
            expected.toByteArray(Charsets.US_ASCII),
            signature.lowercase().toByteArray(Charsets.US_ASCII),
        )
    }

    @Synchronized
    private fun claim(context: Context, requestId: String): Boolean {
        val prefs = context.getSharedPreferences("hakim_signed_task_ids", Context.MODE_PRIVATE)
        if (prefs.contains(requestId)) return false
        return prefs.edit().putLong(requestId, System.currentTimeMillis()).commit()
    }

    private fun fail(context: Context, reason: String): String {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("last_signed_task", reason)
            .putLong("last_signed_task_ms", System.currentTimeMillis())
            .apply()
        return reason
    }

    private val ALLOWED_ACTIONS = setOf(
        "browser_open", "open_url", "browser_back", "back", "browser_forward",
        "browser_reload", "home", "local_proof", "click_text", "click_css", "set_text", "tap",
        "swipe", "scroll_by",
    )
}
