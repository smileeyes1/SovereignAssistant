package org.hakim.omega.companion

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handlePairIntent(intent)
        buildUi()
        ensureNotificationPermission()
        HakimForegroundService.start(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handlePairIntent(intent)
        refreshStatus()
    }

    private fun handlePairIntent(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme == "hakim" && uri.host == "pair") {
            val token = uri.getQueryParameter("token").orEmpty()
            if (token.length >= 32 && token.length <= 256) {
                getSharedPreferences("hakim", MODE_PRIVATE).edit().putString("pair_token", token).apply()
                HakimForegroundService.start(this)
            }
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply {
            text = "HAKIM Ω Companion"
            textSize = 26f
        })
        root.addView(TextView(this).apply {
            text = "طبقة تحكم محلية على هذا الهاتف فقط. لا تعمل السيطرة على الواجهة أو الإشعارات إلا بعد موافقتك من إعدادات Android."
            textSize = 16f
        })
        status = TextView(this).apply { textSize = 16f; setPadding(0, 24, 0, 24) }
        root.addView(status)
        root.addView(button("تفعيل التحكم بالواجهة (Accessibility)") {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        root.addView(button("تفعيل الوصول إلى الإشعارات") {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        root.addView(button("فتح إعدادات بطارية HAKIM") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        root.addView(button("تشغيل الخدمة المحلية") { HakimForegroundService.start(this); refreshStatus() })
        setContentView(root)
        refreshStatus()
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { block() }
    }

    private fun refreshStatus() {
        val paired = getSharedPreferences("hakim", MODE_PRIVATE).getString("pair_token", null) != null
        status.text = "الاقتران المحلي: ${if (paired) "مفعّل" else "غير مفعّل"}\n" +
            "Accessibility: ${if (HakimAccessibilityService.instance != null) "متصل" else "غير متصل"}\n" +
            "الخادم المحلي: ${if (HakimForegroundService.running) "يعمل على 127.0.0.1:47651" else "متوقف"}"
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }
}
