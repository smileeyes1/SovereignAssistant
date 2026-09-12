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
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var qualification: TextView
    private lateinit var browser: WebView
    private lateinit var address: EditText
    private val qualificationExecutor = Executors.newSingleThreadExecutor()
    @Volatile private var qualificationRunning = false

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

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) refreshStatus()
    }

    override fun onDestroy() {
        qualificationExecutor.shutdownNow()
        if (::browser.isInitialized) {
            HakimBrowserController.detach(browser)
            browser.destroy()
        }
        super.onDestroy()
    }

    @Deprecated("Deprecated in Android API; retained for broad device compatibility")
    override fun onBackPressed() {
        if (::browser.isInitialized && browser.canGoBack()) browser.goBack() else super.onBackPressed()
    }

    private fun handlePairIntent(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme != "hakim" || uri.host != "pair") return
        val token = uri.getQueryParameter("token").orEmpty()
        if (token.length !in 32..256) return

        getSharedPreferences("hakim", MODE_PRIVATE).edit().putString("pair_token", token).apply()

        val relayTopic = uri.getQueryParameter("relay_topic")
        val resultTopic = uri.getQueryParameter("result_topic")
        val relayKey = uri.getQueryParameter("relay_key")
        if (!relayTopic.isNullOrBlank() || !resultTopic.isNullOrBlank() || !relayKey.isNullOrBlank()) {
            HakimDirectRelay.configure(
                this,
                relayTopic,
                resultTopic,
                relayKey,
                uri.getQueryParameter("relay_base"),
            )
        }
        if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.restart(this)
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 30, 24, 20)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply { text = "حكيم"; textSize = 27f })
        root.addView(TextView(this).apply {
            text = "النواة الآمنة ٠٫٤٫١: قناة مشفّرة مباشرة + متصفح حكيم المملوك، بلا وصول عام لشاشة الهاتف أو إشعارات التطبيقات."
            textSize = 14f
        })

        status = TextView(this).apply { textSize = 13f; setPadding(0, 12, 0, 8) }
        root.addView(status)

        qualification = TextView(this).apply { textSize = 13f; setPadding(0, 4, 0, 8) }
        root.addView(qualification)

        address = EditText(this).apply { hint = "اكتب عنوان الموقع"; isSingleLine = true }
        root.addView(address, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        val nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        nav.addView(button("فتح") { HakimBrowserController.openUrl(address.text.toString()); refreshStatus() })
        nav.addView(button("رجوع") { HakimBrowserController.action(org.json.JSONObject().put("action", "browser_back")) })
        nav.addView(button("تحديث") { HakimBrowserController.action(org.json.JSONObject().put("action", "browser_reload")) })
        root.addView(nav)

        val safety = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        safety.addView(button("الوضع المالي الآمن") { FinancialSafeMode.enter(this); refreshStatus() })
        safety.addView(button("استعادة حكيم") {
            FinancialSafeMode.exit(this)
            HakimForegroundService.start(this)
            refreshStatus()
        })
        root.addView(safety)

        val serviceControls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        serviceControls.addView(button("إعدادات البطارية") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        serviceControls.addView(button("تشغيل حكيم") {
            if (!FinancialSafeMode.isEnabled(this)) HakimForegroundService.start(this)
            refreshStatus()
        })
        root.addView(serviceControls)

        val qualificationControls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        qualificationControls.addView(button("تأهيل حكيم") { runFieldQualification() })
        root.addView(qualificationControls)

        browser = WebView(this).apply {
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val scheme = request.url.scheme.orEmpty().lowercase()
                    return scheme != "http" && scheme != "https"
                }
                override fun onPageFinished(view: WebView, url: String) {
                    address.setText(url)
                    refreshStatus()
                }
            }
        }
        HakimBrowserController.attach(browser)
        root.addView(browser, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        refreshStatus()
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply {
        text = label
        textSize = 12f
        setOnClickListener { block() }
    }

    private fun runFieldQualification() {
        if (qualificationRunning) return
        if (FinancialSafeMode.isEnabled(this)) {
            qualification.text = "التأهيل الذاتي متوقف: الوضع المالي الآمن مفعّل ولن يعطّله حكيم تلقائيًا"
            return
        }
        qualificationRunning = true
        qualification.text = "التأهيل الذاتي: جارٍ فحص الخادم والتشفير والجولة المشفّرة..."
        HakimForegroundService.start(this)
        qualificationExecutor.execute {
            runCatching { FieldQualification.run(applicationContext) }
            runOnUiThread {
                qualificationRunning = false
                refreshStatus()
            }
        }
    }

    private fun refreshStatus() {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        val paired = prefs.getString("pair_token", null) != null
        val configured = HakimDirectRelay.isConfigured(this)
        val financial = FinancialSafeMode.isEnabled(this)
        val relayBase = prefs.getString(HakimDirectRelay.KEY_RELAY_BASE, "https://ntfy.sh") ?: "https://ntfy.sh"
        val lastPoll = prefs.getLong(HakimDirectRelay.KEY_LAST_POLL_MS, 0L)
        val lastError = prefs.getString(HakimDirectRelay.KEY_LAST_ERROR, null)
        val lastResultError = prefs.getString(HakimDirectRelay.KEY_LAST_RESULT_ERROR, null)
        val url = HakimBrowserController.currentUrl().orEmpty()
        status.text = "النمط: نواة آمنة مستقلة — بلا Make وبلا API مدفوع\n" +
            "نطاق التحكم: متصفح حكيم المملوك فقط\n" +
            "وصول عام لشاشة الهاتف: غير موجود في هذه النسخة\n" +
            "وصول لإشعارات التطبيقات: غير موجود في هذه النسخة\n" +
            "الوضع المالي الآمن: ${if (financial) "مفعّل — حكيم مفصول" else "غير مفعّل"}\n" +
            "الاقتران: ${if (paired) "مفعّل" else "غير مفعّل"}\n" +
            "القناة المشفّرة: ${if (configured) "مهيأة" else "غير مهيأة"}\n" +
            "الناقل: $relayBase\n" +
            "الخادم المحلي: ${if (HakimForegroundService.running) "يعمل" else "متوقف"}\n" +
            "آخر اتصال بالقناة: ${if (lastPoll > 0L) "تم" else "لم يُثبت بعد"}\n" +
            "خطأ القناة: ${lastError ?: "لا يوجد"}\n" +
            "خطأ إرسال النتيجة: ${lastResultError ?: "لا يوجد"}\n" +
            "متصفح حكيم: ${if (HakimBrowserController.isAttached()) "جاهز" else "غير جاهز"}" +
            if (url.isNotBlank()) "\nالموقع الحالي: $url" else ""
        if (::qualification.isInitialized && !qualificationRunning) {
            qualification.text = FieldQualification.lastSummary(this)
        }
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }
}
