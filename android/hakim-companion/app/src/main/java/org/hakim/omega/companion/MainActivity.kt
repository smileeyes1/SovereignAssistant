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
        if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
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
                HakimRemoteRelay.configure(
                    this,
                    uri.getQueryParameter("relay_topic"),
                    uri.getQueryParameter("result_url"),
                    uri.getQueryParameter("relay_key"),
                )
                if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
            }
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply { text = "HAKIM Ω Companion"; textSize = 26f })
        root.addView(TextView(this).apply {
            text = "طبقة تحكم محلية مع قناة اتصال صادرة وموقعة. لا تحتاج خيارات المطور للتشغيل المعتاد. قبل استخدام تطبيق مالي شغّل «الوضع المالي الآمن» لفصل قناة حكيم وخدمة الوصول ومستمع الإشعارات حتى تعيد التفعيل بنفسك."
            textSize = 16f
        })
        status = TextView(this).apply { textSize = 16f; setPadding(0, 24, 0, 24) }
        root.addView(status)
        root.addView(button("تشغيل الوضع المالي الآمن") { FinancialSafeMode.enter(this); refreshStatus() })
        root.addView(button("استعادة حكيم بعد الانتهاء") {
            FinancialSafeMode.exit(this)
            refreshStatus()
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        root.addView(button("تفعيل التحكم بالواجهة") {
            if (!FinancialSafeMode.isEnabled(this)) startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        root.addView(button("تفعيل الوصول إلى الإشعارات") {
            if (!FinancialSafeMode.isEnabled(this)) startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        root.addView(button("فتح إعدادات بطارية حكيم") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        root.addView(button("تشغيل خدمة حكيم") {
            if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
            refreshStatus()
        })
        setContentView(root)
        refreshStatus()
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply { text = label; setOnClickListener { block() } }

    private fun refreshStatus() {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        val paired = prefs.getString("pair_token", null) != null
        val relay = !prefs.getString(HakimRemoteRelay.KEY_TOPIC, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RESULT_URL, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RELAY_KEY, null).isNullOrBlank()
        val financial = FinancialSafeMode.isEnabled(this)
        status.text = "الوضع المالي الآمن: ${if (financial) "مفعّل — حكيم مفصول" else "غير مفعّل"}\n" +
            "خيارات المطور: غير مطلوبة للتشغيل المعتاد\n" +
            "الاقتران المحلي: ${if (paired) "مفعّل" else "غير مفعّل"}\n" +
            "القناة البعيدة الموقعة: ${if (relay) "مهيأة" else "غير مهيأة"}\n" +
            "التحكم بالواجهة: ${if (HakimAccessibilityService.instance != null) "متصل" else "غير متصل"}\n" +
            "الوصول إلى الإشعارات: ${if (HakimNotificationListener.isConnected()) "متصل" else "غير متصل"}\n" +
            "الخادم المحلي: ${if (HakimForegroundService.running) "يعمل محليًا" else "متوقف"}"
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }
}
