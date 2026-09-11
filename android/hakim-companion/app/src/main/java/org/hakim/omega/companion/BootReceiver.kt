package org.hakim.omega.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_LOCKED_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) return
        if (FinancialSafeMode.isEnabled(context)) return
        val token = context.getSharedPreferences("hakim", Context.MODE_PRIVATE).getString("pair_token", null)
        if (token != null) HakimForegroundService.start(context)
    }
}
