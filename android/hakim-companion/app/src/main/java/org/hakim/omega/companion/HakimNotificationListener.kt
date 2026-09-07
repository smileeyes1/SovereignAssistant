package org.hakim.omega.companion

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque

class HakimNotificationListener : NotificationListenerService() {
    override fun onListenerConnected() {
        instance = this
        super.onListenerConnected()
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
        super.onListenerDisconnected()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val extras = sbn.notification.extras
        val item = JSONObject()
            .put("package", sbn.packageName)
            .put("title", extras.getCharSequence("android.title")?.toString().orEmpty())
            .put("text", extras.getCharSequence("android.text")?.toString().orEmpty())
            .put("posted_at", sbn.postTime)
        synchronized(recent) {
            recent.addFirst(item)
            while (recent.size > 100) recent.removeLast()
        }
    }

    companion object {
        @Volatile var instance: HakimNotificationListener? = null
            private set
        private val recent = ArrayDeque<JSONObject>()
        fun isConnected(): Boolean = instance != null
        fun snapshot(): JSONArray = JSONArray().also { arr -> synchronized(recent) { recent.forEach { arr.put(it) } } }
    }
}
