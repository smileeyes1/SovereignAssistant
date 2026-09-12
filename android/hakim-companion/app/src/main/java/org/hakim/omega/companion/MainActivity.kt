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
        if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
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
            text = "التأهيل الميداني الحالي قد يستخدم Termux والتصحيح اللاسلكي وفق سياسة حكيم الحاكمة. أمّا Companion نفسه فمصمم ليعمل لاحقًا دون ADB بعد أن يثبت نجاحه على الهاتف الحقيقي. استخدم «أفضل خطوة قادمة» فقط للموافقات المحلية التي يفرضها أندرويد. وإذا قيّد Android 15 إمكانية الوصول أو الإشعارات بسبب التثبيت الخارجي، افتح «معلومات حكيم» وأكد بنفسك «السماح بالإعدادات المقيّدة» إن ظهر؛ حكيم لا يتجاوز هذا التأكيد الأمني."
            textSize = 16f
        })
        status = TextView(this).apply { textSize = 16f; setPadding(0, 24, 0, 24) }
        root.addView(status)
        root.addView(button("أفضل خطوة قادمة — إكمال إعداد Companion") { continueSetup() })
        root.addView(button("معلومات حكيم — السماح بالإعدادات المقيّدة إن ظهرت") { openAppInfo() })
        root.addView(button("تشغيل الوضع المالي الآمن") { FinancialSafeMode.enter(this); refreshStatus() })
        root.addView(button("استعادة حكيم بعد الانتهاء") {
            FinancialSafeMode.exit(this)
            if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
            refreshStatus()
            continueSetup()
        })
        root.addView(button("تفعيل التحكم بالواجهة") {
            if (!FinancialSafeMode.isEnabled(this)) startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        root.addView(button("تفعيل الوصول إلى الإشعارات") {
            if (!FinancialSafeMode.isEnabled(this)) startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        root.addView(button("فتح إعدادات تطبيق حكيم") { openAppInfo() })
        root.addView(button("تشغيل خدمة Companion") {
            if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
            refreshStatus()
        })
        setContentView(root)
        refreshStatus()
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { block() }
    }

    private fun openAppInfo() {
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
    }

    private fun notificationPermissionGranted(): Boolean =
        Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun paired(): Boolean =
        getSharedPreferences("hakim", MODE_PRIVATE).getString("pair_token", null) != null

    private fun relayConfigured(): Boolean {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        return !prefs.getString(HakimRemoteRelay.KEY_TOPIC, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RESULT_URL, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RELAY_KEY, null).isNullOrBlank()
    }

    private fun continueSetup() {
        if (FinancialSafeMode.isEnabled(this)) {
            FinancialSafeMode.exit(this)
            HakimForegroundService.start(this)
        }
        when {
            !notificationPermissionGranted() -> {
                if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
            }
            !paired() || !relayConfigured() -> {
                refreshStatus("بانتظار تهيئة قناة Companion الخاصة بعد اكتمال مرحلة FIELD الحالية أو أثناء اختبار المرشح.")
            }
            HakimAccessibilityService.instance == null -> {
                refreshStatus("الخطوة الحالية: فعّل «حكيم» في إمكانية الوصول. إذا قال النظام إن الإعداد مقيّد، ارجع وافتح «معلومات حكيم» واسمح بالإعداد المقيّد ثم أعد هذه الخطوة.")
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
            !HakimNotificationListener.isConnected() -> {
                refreshStatus("الخطوة الحالية: اسمح لحكيم بالوصول إلى الإشعارات. إذا ظهر تقييد Android 15، استخدم «معلومات حكيم» ثم أعد المحاولة.")
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
            else -> {
                HakimForegroundService.start(this)
                refreshStatus("✅ Companion جاهز لاختبارات المرشح الحية. لا يُرقّى لمسار التشغيل الحاكم ولا يُغلق ADB قبل نجاح الجولة الميدانية المطلوبة.")
            }
        }
    }

    private fun refreshStatus(note: String? = null) {
        val financial = FinancialSafeMode.isEnabled(this)
        val ready = paired() && relayConfigured() && HakimAccessibilityService.instance != null && HakimNotificationListener.isConnected()
        status.text = buildString {
            if (!note.isNullOrBlank()) append(note).append("\n\n")
            append("الوضع المالي الآمن: ").append(if (financial) "مفعّل — حكيم مفصول" else "غير مفعّل").append('\n')
            append("FIELD الحالي: Termux/ADB حسب السياسة الحاكمة حتى اكتمال الدليل").append('\n')
            append("Companion بعد الترقية: لا يحتاج ADB عند ثبوت الاستقلال").append('\n')
            append("اقتران Companion المحلي: ").append(if (paired()) "مفعّل" else "غير مفعّل").append('\n')
            append("قناة Companion الموقعة: ").append(if (relayConfigured()) "مهيأة" else "غير مهيأة").append('\n')
            append("التحكم بالواجهة: ").append(if (HakimAccessibilityService.instance != null) "متصل" else "غير متصل").append('\n')
            append("الوصول إلى الإشعارات: ").append(if (HakimNotificationListener.isConnected()) "متصل" else "غير متصل").append('\n')
            append("الخادم المحلي: ").append(if (HakimForegroundService.running) "يعمل محليًا" else "متوقف").append('\n')
            append("حالة مرشح Companion: ").append(if (ready && !financial) "جاهز للاختبار الحي" else "غير مكتمل بعد")
        }
    }
}
