package org.hakim.omega.companion

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.lang.ref.WeakReference
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** متصفح حكيم المملوك داخل التطبيق؛ يعمل بجانب خدمات الجهاز ولا يستبدلها. */
object HakimBrowserController {
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var ref: WeakReference<WebView>? = null
    @Volatile private var appContext: Context? = null

    private class GovernanceBridge(private val context: Context) {
        @JavascriptInterface
        fun prepare(text: String?, pageUrl: String?): String =
            HakimAiGovernance.prepare(context, text.orEmpty(), pageUrl)

        @JavascriptInterface
        fun isSupported(pageUrl: String?): Boolean = HakimAiGovernance.isSupportedUrl(pageUrl)

        @JavascriptInterface
        fun version(): String = HakimAiGovernance.VERSION
    }

    fun attach(context: Context, webView: WebView) {
        ref = WeakReference(webView)
        appContext = context.applicationContext
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setSupportMultipleWindows(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        if (android.os.Build.VERSION.SDK_INT >= 26) webView.settings.safeBrowsingEnabled = true
        webView.addJavascriptInterface(GovernanceBridge(context.applicationContext), "HakimNative")
    }

    fun detach(webView: WebView) {
        if (ref?.get() === webView) {
            runCatching { webView.removeJavascriptInterface("HakimNative") }
            ref = null
            appContext = null
        }
    }

    fun isAttached(): Boolean = ref?.get() != null
    fun currentUrl(): String? = onMain<String?>(null) { it.url }
    fun currentTitle(): String? = onMain<String?>(null) { it.title }
    fun governanceStatus(): String = appContext?.let { HakimAiGovernance.status(it) } ?: "حوكمة الذكاء: غير متصلة"

    fun installGovernanceHooks(): Boolean = onMain(false) { webView ->
        val url = webView.url
        if (!HakimAiGovernance.isSupportedUrl(url)) return@onMain false
        webView.evaluateJavascript(GOVERNANCE_HOOK_JS, null)
        true
    }

    fun openUrl(raw: String): Boolean {
        val url = normalizeUrl(raw) ?: return false
        return onMain(false) { it.loadUrl(url); true }
    }

    fun openChatGpt(): Boolean = openUrl("https://chatgpt.com/")

    fun action(obj: JSONObject): Boolean = when (obj.optString("action")) {
        "browser_open", "open_url" -> openUrl(obj.optString("url"))
        "browser_back" -> onMain(false) { if (it.canGoBack()) { it.goBack(); true } else false }
        "browser_forward" -> onMain(false) { if (it.canGoForward()) { it.goForward(); true } else false }
        "browser_reload" -> onMain(false) { it.reload(); true }
        "click_text" -> clickText(obj.optString("text"))
        "click_css" -> clickCss(obj.optString("selector"))
        "set_text" -> setText(obj.optString("id"), obj.optString("text"), obj.optString("value"))
        "tap" -> tap(obj.optDouble("x"), obj.optDouble("y"))
        "swipe" -> swipe(obj.optDouble("x1"), obj.optDouble("y1"), obj.optDouble("x2"), obj.optDouble("y2"))
        "scroll_by" -> scrollBy(obj.optDouble("x"), obj.optDouble("y"))
        else -> false
    }

    fun uiSnapshot(limit: Int = 200): JSONArray {
        val safeLimit = limit.coerceIn(1, 300)
        val js = """
            (function(){
              const all=[...document.querySelectorAll('a,button,input,textarea,select,[role="button"],[contenteditable="true"]')];
              return all.filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;}).slice(0,$safeLimit).map((e,i)=>{
                const r=e.getBoundingClientRect();
                return {i:i,tag:(e.tagName||'').toLowerCase(),text:String(e.innerText||e.value||e.getAttribute('aria-label')||e.getAttribute('placeholder')||'').slice(0,500),id:e.id||'',name:e.getAttribute('name')||'',type:e.getAttribute('type')||'',href:e.href||'',disabled:!!e.disabled,rect:[Math.round(r.left),Math.round(r.top),Math.round(r.right),Math.round(r.bottom)]};
              });
            })()
        """.trimIndent()
        val raw = eval(js) ?: return JSONArray()
        return runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
    }

    fun status(): JSONObject = JSONObject()
        .put("attached", isAttached())
        .put("url", currentUrl() ?: JSONObject.NULL)
        .put("title", currentTitle() ?: JSONObject.NULL)
        .put("mode", "OWNED_BROWSER_GOVERNED_AI")
        .put("governance_version", HakimAiGovernance.VERSION)

    fun screenshotBase64(): String? = onMain<String?>(null, 5_000L) { w ->
        // A URL can already be committed while Android is still finishing the first layout pass.
        // Use the measured/display bounds as a fail-safe so the control plane does not report a
        // false "screenshot unavailable" merely because width/height have not propagated yet.
        val dm = w.resources.displayMetrics
        val width = sequenceOf(w.width, w.measuredWidth, dm.widthPixels)
            .firstOrNull { it > 0 } ?: return@onMain null
        val height = sequenceOf(w.height, w.measuredHeight, dm.heightPixels / 2)
            .firstOrNull { it > 0 } ?: return@onMain null
        val bmp = Bitmap.createBitmap(width.coerceAtMost(4096), height.coerceAtMost(4096), Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        w.draw(canvas)
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.PNG, 90, out)
        bmp.recycle()
        Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    private fun clickText(text: String): Boolean {
        if (text.isBlank() || text.length > 500) return false
        val q = JSONObject.quote(text.trim())
        return evalBoolean("(function(){const q=$q;const els=[...document.querySelectorAll('button,a,input[type=\"button\"],input[type=\"submit\"],[role=\"button\"]')];const e=els.find(x=>String(x.innerText||x.value||x.getAttribute('aria-label')||'').trim().includes(q));if(!e)return false;e.click();return true;})()")
    }

    private fun clickCss(selector: String): Boolean {
        if (selector.isBlank() || selector.length > 500) return false
        val s = JSONObject.quote(selector)
        return evalBoolean("(function(){try{const e=document.querySelector($s);if(!e)return false;e.click();return true;}catch(_){return false;}})()")
    }

    private fun setText(id: String, hint: String, value: String): Boolean {
        if (value.length > 50_000 || id.length > 500 || hint.length > 500) return false
        val i = JSONObject.quote(id); val h = JSONObject.quote(hint); val v = JSONObject.quote(value)
        return evalBoolean("""
            (function(){const id=$i,h=$h,v=$v;let e=id?document.getElementById(id):null;
            if(!e&&h){e=[...document.querySelectorAll('input,textarea,[contenteditable="true"]')].find(x=>String(x.getAttribute('placeholder')||x.getAttribute('aria-label')||x.getAttribute('name')||x.innerText||'').includes(h));}
            if(!e)return false;e.focus();if('value' in e){const p=Object.getPrototypeOf(e);const d=p?Object.getOwnPropertyDescriptor(p,'value'):null;if(d&&d.set)d.set.call(e,v);else e.value=v;}else{e.textContent=v;}e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:v}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()
        """.trimIndent())
    }

    private fun tap(x: Double, y: Double): Boolean {
        if (!x.isFinite() || !y.isFinite()) return false
        return evalBoolean("(function(){const e=document.elementFromPoint(${x.toInt()},${y.toInt()});if(!e)return false;e.click();return true;})()")
    }

    private fun swipe(x1: Double, y1: Double, x2: Double, y2: Double): Boolean {
        if (!x1.isFinite() || !y1.isFinite() || !x2.isFinite() || !y2.isFinite()) return false
        return scrollBy(x1 - x2, y1 - y2)
    }

    private fun scrollBy(x: Double, y: Double): Boolean {
        if (!x.isFinite() || !y.isFinite()) return false
        return evalBoolean("(function(){window.scrollBy(${x.toInt()},${y.toInt()});return true;})()")
    }

    private fun evalBoolean(script: String): Boolean = eval(script)?.trim()?.equals("true", ignoreCase = true) == true

    private fun eval(script: String, timeoutMs: Long = 4_000L): String? {
        val w = ref?.get() ?: return null
        if (Looper.myLooper() == Looper.getMainLooper()) return null
        val latch = CountDownLatch(1)
        var result: String? = null
        main.post { runCatching { w.evaluateJavascript(script) { value -> result = value; latch.countDown() } }.onFailure { latch.countDown() } }
        latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        return result
    }

    private fun normalizeUrl(raw: String): String? {
        val value = raw.trim()
        if (value.isBlank() || value.length > 4096) return null
        val candidate = if (value.startsWith("http://") || value.startsWith("https://")) value else "https://$value"
        val uri = runCatching { android.net.Uri.parse(candidate) }.getOrNull() ?: return null
        return if (uri.scheme == "http" || uri.scheme == "https") candidate else null
    }

    private fun <T> onMain(default: T, timeoutMs: Long = 3_000L, block: (WebView) -> T): T {
        val w = ref?.get() ?: return default
        if (Looper.myLooper() == Looper.getMainLooper()) return runCatching { block(w) }.getOrDefault(default)
        val latch = CountDownLatch(1); var out = default
        main.post { out = runCatching { block(w) }.getOrDefault(default); latch.countDown() }
        latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        return out
    }

    /**
     * اعتراض محلي قبل الإرسال فقط على منصات الذكاء المسموحة. لا يمنع المنصة من
     * تطبيق تعليماتها الأعلى، ولا يقرأ كلمات المرور أو الحقول غير النصية.
     */
    private const val GOVERNANCE_HOOK_JS = """
(function(){
  try {
    if (!window.HakimNative || !HakimNative.isSupported(String(location.href))) return false;
    if (window.__hakimGovernanceInstalled === '1.0.0') return true;
    window.__hakimGovernanceInstalled = '1.0.0';
    const marker='[[HAKIM::GOVERNED::v1]]';
    function editor(){
      const a=document.activeElement;
      if(a && (a.tagName==='TEXTAREA' || a.getAttribute('contenteditable')==='true')) return a;
      return document.querySelector('textarea,[contenteditable="true"],[role="textbox"]');
    }
    function getText(e){
      if(!e) return '';
      if('value' in e) return String(e.value||'');
      return String(e.innerText||e.textContent||'');
    }
    function setText(e,v){
      if(!e) return false;
      e.focus();
      if('value' in e){
        let p=e; let d=null;
        while(p && !d){ p=Object.getPrototypeOf(p); if(p)d=Object.getOwnPropertyDescriptor(p,'value'); }
        if(d && d.set)d.set.call(e,v); else e.value=v;
      } else {
        e.textContent=v;
      }
      e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:v}));
      e.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    }
    function govern(){
      const e=editor(); const raw=getText(e).trim();
      if(!raw || raw.startsWith(marker)) return false;
      const wrapped=String(HakimNative.prepare(raw,String(location.href))||'');
      if(!wrapped || wrapped===raw) return false;
      return setText(e,wrapped);
    }
    document.addEventListener('keydown',function(ev){
      if(ev.key==='Enter' && !ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey) govern();
    },true);
    document.addEventListener('click',function(ev){
      let n=ev.target;
      for(let i=0;n&&i<5;i++,n=n.parentElement){
        const t=String((n.innerText||'')+' '+(n.getAttribute?.('aria-label')||'')+' '+(n.getAttribute?.('data-testid')||'')).toLowerCase();
        if(/send|submit|إرسال|ارسال|prompt-submit|composer-submit/.test(t)){ govern(); break; }
      }
    },true);
    return true;
  } catch(e) { return false; }
})()
"""
}
