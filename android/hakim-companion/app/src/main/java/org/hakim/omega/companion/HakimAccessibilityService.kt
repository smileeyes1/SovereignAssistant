package org.hakim.omega.companion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Bitmap
import android.graphics.ColorSpace
import android.graphics.Path
import android.os.Bundle
import android.util.Base64
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class HakimAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() { instance = this }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}
    override fun onDestroy() { if (instance === this) instance = null; super.onDestroy() }

    fun uiSnapshot(limit: Int = 250): JSONArray {
        val arr = JSONArray(); val root = rootInActiveWindow ?: return arr
        val queue = ArrayDeque<AccessibilityNodeInfo>(); queue.add(root)
        while (queue.isNotEmpty() && arr.length() < limit) {
            val n = queue.removeFirst(); val r = android.graphics.Rect(); n.getBoundsInScreen(r)
            arr.put(JSONObject()
                .put("package", n.packageName?.toString().orEmpty())
                .put("text", n.text?.toString().orEmpty())
                .put("desc", n.contentDescription?.toString().orEmpty())
                .put("id", n.viewIdResourceName.orEmpty())
                .put("class", n.className?.toString().orEmpty())
                .put("clickable", n.isClickable)
                .put("editable", n.isEditable)
                .put("scrollable", n.isScrollable)
                .put("bounds", JSONArray(listOf(r.left, r.top, r.right, r.bottom))))
            for (i in 0 until n.childCount) n.getChild(i)?.let { queue.add(it) }
        }
        return arr
    }

    fun action(obj: JSONObject): Boolean = when (obj.optString("action")) {
        "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
        "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
        "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
        "notifications" -> performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
        "quick_settings" -> performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
        "click_text" -> clickText(obj.optString("text"))
        "set_text" -> setText(obj.optString("id"), obj.optString("text"), obj.optString("value"))
        "tap" -> tap(obj.optDouble("x").toFloat(), obj.optDouble("y").toFloat())
        "swipe" -> swipe(obj.optDouble("x1").toFloat(), obj.optDouble("y1").toFloat(), obj.optDouble("x2").toFloat(), obj.optDouble("y2").toFloat(), obj.optLong("duration", 400))
        else -> false
    }

    private fun clickText(text: String): Boolean {
        if (text.isBlank()) return false
        val root = rootInActiveWindow ?: return false
        for (n in root.findAccessibilityNodeInfosByText(text)) {
            var cur: AccessibilityNodeInfo? = n
            repeat(5) {
                if (cur?.isClickable == true) return cur!!.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                cur = cur?.parent
            }
        }
        return false
    }

    private fun setText(id: String, textHint: String, value: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val nodes = when {
            id.isNotBlank() -> root.findAccessibilityNodeInfosByViewId(id)
            textHint.isNotBlank() -> root.findAccessibilityNodeInfosByText(textHint)
            else -> emptyList()
        }
        val b = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value) }
        return nodes.firstOrNull { it.isEditable }?.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, b) == true
    }

    private fun tap(x: Float, y: Float): Boolean {
        val p = Path().apply { moveTo(x, y) }
        return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(p, 0, 80)).build(), null, null)
    }

    private fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, duration: Long): Boolean {
        val p = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(p, 0, duration.coerceIn(100, 3000))).build(), null, null)
    }

    fun screenshotBase64(): String? {
        if (android.os.Build.VERSION.SDK_INT < 30) return null
        val latch = CountDownLatch(1); var result: String? = null
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onSuccess(s: ScreenshotResult) {
                try {
                    val hw = s.hardwareBuffer
                    val bmp = Bitmap.wrapHardwareBuffer(hw, s.colorSpace ?: ColorSpace.get(ColorSpace.Named.SRGB))
                    val copy = bmp?.copy(Bitmap.Config.ARGB_8888, false)
                    val out = ByteArrayOutputStream(); copy?.compress(Bitmap.CompressFormat.PNG, 90, out)
                    result = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
                    copy?.recycle(); hw.close()
                } catch (_: Exception) {} finally { latch.countDown() }
            }
            override fun onFailure(errorCode: Int) { latch.countDown() }
        })
        latch.await(3, TimeUnit.SECONDS)
        return result
    }

    companion object { @Volatile var instance: HakimAccessibilityService? = null }
}
