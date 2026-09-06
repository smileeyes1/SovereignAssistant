package org.hakim.omega.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

class HakimForegroundService : Service() {
    private var server: LocalControlServer? = null

    override fun onCreate() {
        super.onCreate()
        running = true
        createChannel()
        val notification = android.app.Notification.Builder(this, CHANNEL)
            .setContentTitle("HAKIM Ω")
            .setContentText("التحكم المحلي جاهز — 127.0.0.1 فقط")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(7, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else startForeground(7, notification)
        server = LocalControlServer(this).also { it.start() }
    }

    override fun onDestroy() {
        server?.close()
        server = null
        running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "HAKIM Ω Local Control", NotificationManager.IMPORTANCE_LOW))
        }
    }

    companion object {
        const val CHANNEL = "hakim_local_control"
        @Volatile var running = false
        fun start(context: Context) {
            val i = Intent(context, HakimForegroundService::class.java)
            try { context.startForegroundService(i) } catch (_: Exception) { try { context.startService(i) } catch (_: Exception) {} }
        }
    }
}
