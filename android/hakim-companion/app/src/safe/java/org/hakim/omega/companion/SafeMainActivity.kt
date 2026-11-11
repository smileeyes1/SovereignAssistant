package org.hakim.omega.companion

import android.app.Activity
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

/**
 * نسخة التثبيت الآمنة: متصفح حكيم والحوكمة فقط.
 * لا Accessibility، لا Notification Listener، لا foreground control service، ولا ADB.
 */
class SafeMainActivity : Activity() {
    private lateinit var browser: WebView
    private lateinit var address: EditText
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
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

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 30, 24, 20)
            gravity = Gravity.CENTER_HORIZONTAL
        }

        root.addView(TextView(this).apply {
            text = "حكيم"
            textSize = 27f
        })
        root.addView(TextView(this).apply {
            text = "نسخة التثبيت الآمنة — متصفح ذكاء محكوم محليًا. لا تطلب صلاحيات وصول حساسة، ولا تتحكم بالجهاز، ولا تقرأ الإشعارات."
            textSize = 14f
        })

        status = TextView(this).apply {
            textSize = 13f
            setPadding(0, 12, 0, 8)
        }
        root.addView(status)

        address = EditText(this).apply {
            hint = "اكتب عنوان الموقع"
            isSingleLine = true
        }
        root.addView(address, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        val nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        nav.addView(button("ChatGPT عبر حكيم") {
            HakimBrowserController.openChatGpt()
            refreshStatus()
        })
        nav.addView(button("فتح") {
            HakimBrowserController.openUrl(address.text.toString())
            refreshStatus()
        })
        nav.addView(button("رجوع") {
            HakimBrowserController.action(org.json.JSONObject().put("action", "browser_back"))
        })
        nav.addView(button("تحديث") {
            HakimBrowserController.action(org.json.JSONObject().put("action", "browser_reload"))
        })
        root.addView(nav)

        browser = WebView(this).apply {
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val scheme = request.url.scheme.orEmpty().lowercase()
                    return scheme != "http" && scheme != "https"
                }

                override fun onPageFinished(view: WebView, url: String) {
                    address.setText(url)
                    HakimBrowserController.installGovernanceHooks()
                    refreshStatus()
                }
            }
        }
        HakimBrowserController.attach(this, browser)
        root.addView(browser, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        setContentView(root)
        refreshStatus()
        HakimBrowserController.openChatGpt()
    }

    private fun button(label: String, block: () -> Unit) = Button(this).apply {
        text = label
        textSize = 12f
        setOnClickListener { block() }
    }

    private fun refreshStatus() {
        val url = if (::browser.isInitialized) HakimBrowserController.currentUrl().orEmpty() else ""
        status.text = "الوضع: تثبيت آمن — متصفح فقط\n" +
            "${HakimBrowserController.governanceStatus()}\n" +
            "صلاحيات حساسة: غير موجودة في هذه النسخة\n" +
            "التحكم بالجهاز: غير موجود في هذه النسخة" +
            if (url.isNotBlank()) "\nالموقع الحالي: $url" else ""
    }
}
