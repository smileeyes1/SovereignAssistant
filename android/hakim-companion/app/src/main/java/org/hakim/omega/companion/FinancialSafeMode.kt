package org.hakim.omega.companion

import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.notification.NotificationListenerService

/**
 * وضع مالي آمن يفصل قدرات التحكم الحساسة قبل استخدام التطبيقات المالية.
 *
 * لا يعتمد على ADB أو خيارات المطور. عند التفعيل:
 * - يوقف قناة حكيم المحلية والبعيدة.
 * - يوقف خدمة إمكانية الوصول ذاتيًا.
 * - يفصل مستمع الإشعارات إن كان متصلًا.
 * - يبقى مفعّلًا عبر إعادة التشغيل حتى يلغيه المستخدم صراحة.
 *
 * إعادة تفعيل Accessibility تبقى فعلًا محليًا صريحًا للمستخدم كما يفرض أندرويد.
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

        runCatching { HakimAccessibilityService.instance?.disableSelf() }
        runCatching { HakimNotificationListener.instance?.requestUnbind() }
        runCatching { context.stopService(Intent(context, HakimForegroundService::class.java)) }
    }

    fun exit(context: Context) {
        context.getSharedPreferences("hakim", Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY, false)
            .putString("companion_mode", "REACTIVATING")
            .apply()

        if (Build.VERSION.SDK_INT >= 24) {
            runCatching {
                NotificationListenerService.requestRebind(
                    ComponentName(context, HakimNotificationListener::class.java),
                )
            }
        }
        HakimForegroundService.start(context)
    }
}

class FinancialSafeModeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == FinancialSafeMode.ACTION_ENTER) {
            FinancialSafeMode.enter(context)
        }
    }
}
