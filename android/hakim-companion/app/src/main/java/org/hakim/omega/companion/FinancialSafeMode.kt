package org.hakim.omega.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * وضع مالي آمن يفصل قناة حكيم وخدمة التحكم قبل استخدام التطبيقات المالية.
 * النسخة الحالية لا تستخدم Accessibility ولا Notification Listener أصلًا.
 */
object FinancialSafeMode {
    const val KEY = "financial_safe_mode"
    const val ACTION_ENTER = "org.hakim.omega.companion.ENTER_FINANCIAL_SAFE_MODE"

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences("hakim", Context.MODE_PRIVATE).getBoolean(KEY, false)

    fun enter(context: Context) {
        context.getSharedPreferences("hakim", Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY, true)
            .putString("companion_mode", "FINANCIAL_SAFE")
            .apply()
        runCatching { context.stopService(Intent(context, HakimForegroundService::class.java)) }
    }

    fun exit(context: Context) {
        context.getSharedPreferences("hakim", Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY, false)
            .putString("companion_mode", "REACTIVATING")
            .apply()
        HakimForegroundService.start(context)
    }
}

class FinancialSafeModeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == FinancialSafeMode.ACTION_ENTER) FinancialSafeMode.enter(context)
    }
}
