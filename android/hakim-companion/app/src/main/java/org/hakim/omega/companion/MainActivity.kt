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
        purgeLegacyTransport()
        handlePairIntent(intent)
        buildUi()
        handleTaskIntent(intent)
        ensureNotificationPermission()
        if (!FinancialSafeMode.isEnabled(this) && isPaired()) HakimForegroundService.start(this)
        refreshStatus()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        purgeLegacyTransport()
        handlePairIntent(intent)
        handleTaskIntent(intent)
        if (!FinancialSafeMode.isEnabled(this) && isPaired()) HakimForegroundService.start(this)
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
        if (uri.scheme != "hakim" || uri.host != "pair") return
        val token = uri.getQueryParameter("token").orEmpty()
        if (token.length !in 32..256) return
        getSharedPreferences("hakim", MODE_PRIVATE).edit()
            .putString("pair_token", token)
            .putString("pair_mode", "SOVEREIGN_LOCAL")
            .apply()
    }

    private fun handleTaskIntent(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme == "hakim" && uri.host == "task") {
            HakimSignedTask.accept(this, uri)
        }
    }

    private fun purgeLegacyTransport() {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        val editor = prefs.edit()
        prefs.all.keys.filter { it.startsWith("relay_") }.forEach { editor.remove(it) }
        editor.apply()
        getSharedPreferences("hakim_remote_pending", MODE_PRIVATE).edit().clear().apply()
    }

    private fun isPaired(): Boolean =
        !getSharedPreferences("hakim", MODE_PRIVATE).getString("pair_token", null).isNullOrBlank()

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 32, 24, 24)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        root.addView(TextView(this).apply { text = "حكيم"; textSize = 27f })
        root.addView(TextView(this).apply {
            text = "القلب السيادي المحلي: لا ناقل خارجي، لا قناة خلفية، لا رصيد عمليات. التحكم المحلي على الجهاز فقط، وأي مهمة قادمة من المحادثة تصل كرابط موقّع يفتحه المستخدم صراحة ثم ينفذها حكيم داخل متصفحه المملوك."
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
        nav.addView(button("فتح") { if (HakimBrowserController.openUrl(address.text.toString())) refreshStatus() })
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
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { block() }
    }

    private fun refreshStatus() {
        val prefs = getSharedPreferences("hakim", MODE_PRIVATE)
        val paired = isPaired()
        val financial = FinancialSafeMode.isEnabled(this)
        val url = HakimBrowserController.currentUrl().orEmpty()
        val lastTask = prefs.getString("last_signed_task", "لا توجد مهمة بعد")
        status.text = "النمط: سيادي محلي مستقل\n" +
            "الوضع المالي الآمن: ${if (financial) "مفعّل — حكيم مفصول" else "غير مفعّل"}\n" +
            "الاقتران المحلي: ${if (paired) "مفعّل" else "غير مفعّل"}\n" +
            "اتصال خلفي خارجي: غير موجود\n" +
            "ناقل خارجي: غير موجود\n" +
            "الخادم المحلي: ${if (HakimForegroundService.running) "يعمل" else "متوقف"}\n" +
            "آخر مهمة موقعة: $lastTask\n" +
            "متصفح حكيم: ${if (HakimBrowserController.isAttached()) "جاهز" else "غير جاهز"}" +
            if (url.isNotBlank()) "\nالموقع الحالي: $url" else ""
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
    }
}
