package org.hakim.omega.companion

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
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

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var browser: WebView
    private lateinit var address: EditText

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
            setPadding(24, 32, 24, 24)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply { text = "حكيم"; textSize = 27f })
        root.addView(TextView(this).apply {
            text = "متصفح حكيم المحلي الآمن: تحكم داخل المتصفح المملوك فقط، بلا صلاحية قراءة الإشعارات وبلا خدمة إمكانية الوصول. قناة حكيم المشفّرة والموافقات الصريحة تبقيان كما هما."
            textSize = 15f
        })

        status = TextView(this).apply { textSize = 14f; setPadding(0, 16, 0, 12) }
        root.addView(status)

        address = EditText(this).apply {
            hint = "اكتب عنوان الموقع"
            isSingleLine = true
        }
        root.addView(address, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        val nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        nav.addView(button("فتح") {
            if (HakimBrowserController.openUrl(address.text.toString())) refreshStatus()
        })
        nav.addView(button("رجوع") { HakimBrowserController.action(org.json.JSONObject().put("action", "browser_back")) })
        nav.addView(button("تحديث") { HakimBrowserController.action(org.json.JSONObject().put("action", "browser_reload")) })
        root.addView(nav)

        val safe = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        safe.addView(button("الوضع المالي الآمن") { FinancialSafeMode.enter(this); refreshStatus() })
        safe.addView(button("استعادة حكيم") { FinancialSafeMode.exit(this); refreshStatus() })
        root.addView(safe)

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
        setOnClickListener { block() }
    }

    private fun refreshStatus() {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        val paired = prefs.getString("pair_token", null) != null
        val relay = !prefs.getString(HakimRemoteRelay.KEY_TOPIC, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RESULT_URL, null).isNullOrBlank() &&
            !prefs.getString(HakimRemoteRelay.KEY_RELAY_KEY, null).isNullOrBlank()
        val financial = FinancialSafeMode.isEnabled(this)
        val url = HakimBrowserController.currentUrl().orEmpty()
        status.text = "الوضع المالي الآمن: ${if (financial) "مفعّل — حكيم مفصول" else "غير مفعّل"}\n" +
            "الاقتران: ${if (paired) "مفعّل" else "غير مفعّل"}\n" +
            "القناة البعيدة المشفّرة: ${if (relay) "مهيأة" else "غير مهيأة"}\n" +
            "الخادم المحلي: ${if (HakimForegroundService.running) "يعمل" else "متوقف"}\n" +
            "متصفح حكيم: ${if (HakimBrowserController.isAttached()) "جاهز" else "غير جاهز"}" +
            if (url.isNotBlank()) "\nالموقع الحالي: $url" else ""
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }
}
