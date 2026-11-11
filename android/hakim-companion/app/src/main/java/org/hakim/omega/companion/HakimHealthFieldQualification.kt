package org.hakim.omega.companion

import android.content.Context
import org.json.JSONObject
import java.time.Instant

object HakimHealthFieldQualification {
    private const val PREFS = "hakim_health_field_qualification"
    private const val KEY_READ_PROVEN = "read_proven"
    private const val KEY_REVOCATION_PROVEN = "revocation_proven"
    private const val KEY_AWAITING_REVOCATION = "awaiting_revocation"
    private const val KEY_HEART_SOURCE_PRESENT = "heart_source_present"
    private const val KEY_LAST_EVENT = "last_event"
    private const val KEY_LAST_EVENT_AT = "last_event_at"

    fun reset(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
    }

    fun markPermissionGranted(context: Context) = markEvent(context, "PERMISSION_GRANTED")

    fun markReadSuccess(context: Context, snapshot: JSONObject) {
        val heartSamples = snapshot.getJSONObject("heart_rate").optInt("sample_count", 0)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY_READ_PROVEN, true)
            .putBoolean(KEY_HEART_SOURCE_PRESENT, heartSamples > 0)
            .putBoolean(KEY_AWAITING_REVOCATION, false)
            .putString(KEY_LAST_EVENT, "LOCAL_READ_PROVEN")
            .putString(KEY_LAST_EVENT_AT, Instant.now().toString())
            .apply()
    }

    fun beginRevocationTest(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY_AWAITING_REVOCATION, true)
            .putString(KEY_LAST_EVENT, "REVOCATION_TEST_REQUESTED")
            .putString(KEY_LAST_EVENT_AT, Instant.now().toString())
            .apply()
    }

    fun markRevocationProven(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY_REVOCATION_PROVEN, true)
            .putBoolean(KEY_AWAITING_REVOCATION, false)
            .putString(KEY_LAST_EVENT, "REVOCATION_FAIL_CLOSED_PROVEN")
            .putString(KEY_LAST_EVENT_AT, Instant.now().toString())
            .apply()
    }

    fun readProven(context: Context): Boolean = prefs(context).getBoolean(KEY_READ_PROVEN, false)
    fun revocationProven(context: Context): Boolean = prefs(context).getBoolean(KEY_REVOCATION_PROVEN, false)
    fun awaitingRevocation(context: Context): Boolean = prefs(context).getBoolean(KEY_AWAITING_REVOCATION, false)
    fun healthGateReady(context: Context): Boolean = readProven(context) && revocationProven(context)

    fun summary(context: Context): String {
        val p = prefs(context)
        val read = p.getBoolean(KEY_READ_PROVEN, false)
        val revoke = p.getBoolean(KEY_REVOCATION_PROVEN, false)
        val source = p.getBoolean(KEY_HEART_SOURCE_PRESENT, false)
        val event = p.getString(KEY_LAST_EVENT, "UNSTARTED") ?: "UNSTARTED"
        return "تأهيل الصحة: قراءة=${if (read) "مثبتة" else "غير مثبتة"}، " +
            "سحب الإذن=${if (revoke) "مثبت" else "غير مثبت"}، " +
            "مصدر نبض فعلي=${if (source) "موجود" else "غير مثبت/لا بيانات"}، " +
            "الحالة=$event، قيم الصحة نفسها غير محفوظة في سجل التأهيل."
    }

    private fun markEvent(context: Context, event: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_LAST_EVENT, event)
            .putString(KEY_LAST_EVENT_AT, Instant.now().toString())
            .apply()
    }

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
