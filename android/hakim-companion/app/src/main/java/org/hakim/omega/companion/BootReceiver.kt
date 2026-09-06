package org.hakim.omega.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val token = context.getSharedPreferences("hakim", Context.MODE_PRIVATE).getString("pair_token", null)
        if (token != null) HakimForegroundService.start(context)
    }
}
