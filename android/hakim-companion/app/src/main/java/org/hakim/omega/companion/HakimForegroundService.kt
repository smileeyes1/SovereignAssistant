package org.hakim.omega.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper

class HakimForegroundService : Service() {
    private var server: LocalControlServer? = null
    private val supervisor = Handler(Looper.getMainLooper())

    private val supervise = object : Runnable {
        override fun run() {
            val prefs = getSharedPreferences("hakim", Context.MODE_PRIVATE)
            val paired = prefs.getString("pair_token", null) != null
            var healthy = paired && server?.isListening() == true

            if (paired && !healthy) {
                server?.close()
                server = LocalControlServer(this@HakimForegroundService).also { it.start() }
                healthy = server?.isListening() == true
            }

            prefs.edit()
                .putLong("companion_heartbeat_ms", System.currentTimeMillis())
                .putString("companion_mode", if (healthy) "HEALTHY" else if (paired) "RECOVERING" else "UNPAIRED")
                .putBoolean("persistent_model", false)
                .apply()

            supervisor.postDelayed(this, SUPERVISOR_INTERVAL_MS)
        }
    }

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
        supervisor.postDelayed(supervise, INITIAL_SUPERVISOR_DELAY_MS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        supervisor.removeCallbacks(supervise)
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
        const val INITIAL_SUPERVISOR_DELAY_MS = 5_000L
        const val SUPERVISOR_INTERVAL_MS = 30_000L
        @Volatile var running = false
        fun start(context: Context) {
            val i = Intent(context, HakimForegroundService::class.java)
            try { context.startForegroundService(i) } catch (_: Exception) { try { context.startService(i) } catch (_: Exception) {} }
        }
    }
}
