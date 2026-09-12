package org.hakim.omega.companion

import android.content.Context
import android.content.Intent
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

class LocalControlServer(private val context: Context) {
    private val pool = Executors.newFixedThreadPool(2)
    @Volatile private var socket: ServerSocket? = null

    fun start() {
        if (isListening()) return
        pool.execute {
            try {
                val s = ServerSocket()
                s.reuseAddress = true
                s.bind(InetSocketAddress(InetAddress.getLoopbackAddress(), PORT))
                socket = s
                while (!s.isClosed) runCatching { s.accept() }.getOrNull()?.let { client -> pool.execute { handle(client) } }
            } catch (_: Exception) { socket = null }
        }
    }

    fun isListening(): Boolean = socket?.let { it.isBound && !it.isClosed } == true
    fun close() { runCatching { socket?.close() }; socket = null; pool.shutdownNow() }

    private fun handle(client: Socket) {
        client.use { c ->
            c.soTimeout = 5000
            val reader = BufferedReader(InputStreamReader(c.getInputStream(), Charsets.UTF_8))
            val request = reader.readLine() ?: return
            val parts = request.split(' '); if (parts.size < 2) return
            val method = parts[0]; val path = parts[1]
            val headers = mutableMapOf<String, String>()
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isBlank()) break
                val i = line.indexOf(':'); if (i > 0) headers[line.substring(0, i).trim().lowercase()] = line.substring(i + 1).trim()
            }
            val len = headers["content-length"]?.toIntOrNull()?.coerceIn(0, 65536) ?: 0
            val chars = CharArray(len); var off = 0
            while (off < len) { val n = reader.read(chars, off, len - off); if (n <= 0) break; off += n }
            val body = String(chars, 0, off)
            val token = context.getSharedPreferences("hakim", Context.MODE_PRIVATE).getString("pair_token", null)
            if (token == null || headers["authorization"] != "Bearer $token") return respond(c, 401, JSONObject().put("error", "unauthorized"))
            route(c, method, path, body, headers)
        }
    }

    private fun route(c: Socket, method: String, path: String, body: String, headers: Map<String, String>) {
        try {
            when {
                method == "GET" && path == "/v1/status" -> {
                    val prefs = context.getSharedPreferences("hakim", Context.MODE_PRIVATE)
                    val heartbeat = prefs.getLong("companion_heartbeat_ms", 0L)
                    respond(c, 200, JSONObject()
                        .put("evidence_state", "NOT_PROVEN")
                        .put("runtime_health", prefs.getString("companion_mode", "UNKNOWN"))
                        .put("loopback_only", true)
                        .put("control_server_listening", isListening())
                        .put("heartbeat_age_ms", if (heartbeat > 0L) (System.currentTimeMillis() - heartbeat).coerceAtLeast(0L) else -1L)
                        .put("persistent_model", JSONObject.NULL)
                        .put("persistent_model_evidence", "NOT_PROVEN")
                        .put("persistent_model_allowed", false)
                        .put("direct_relay_configured", HakimDirectRelay.isConfigured(context))
                        .put("accessibility", HakimAccessibilityService.instance != null)
                        .put("notification_listener", HakimNotificationListener.isConnected())
                        .put("notifications_buffered", HakimNotificationListener.snapshot().length())
                        .put("browser", HakimBrowserController.status()))
                }
                method == "GET" && path == "/v1/ui" -> {
                    val service = HakimAccessibilityService.instance
                    if (service != null) {
                        respond(c, 200, JSONObject().put("mode", "accessibility").put("nodes", service.uiSnapshot()))
                    } else if (HakimBrowserController.isAttached()) {
                        respond(c, 200, JSONObject()
                            .put("mode", "browser_dom")
                            .put("url", HakimBrowserController.currentUrl() ?: JSONObject.NULL)
                            .put("nodes", HakimBrowserController.uiSnapshot()))
                    } else respond(c, 409, JSONObject().put("error", "ui_unavailable"))
                }
                method == "GET" && path == "/v1/notifications" -> {
                    if (!HakimNotificationListener.isConnected()) respond(c, 409, JSONObject().put("error", "notification_listener_unavailable"))
                    else respond(c, 200, JSONObject().put("items", HakimNotificationListener.snapshot()))
                }
                method == "GET" && path == "/v1/screenshot" -> {
                    val accessibilityShot = HakimAccessibilityService.instance?.screenshotBase64()
                    val browserShot = if (accessibilityShot == null) HakimBrowserController.screenshotBase64() else null
                    val data = accessibilityShot ?: browserShot
                    if (data == null) respond(c, 409, JSONObject().put("error", "screenshot_unavailable"))
                    else respond(c, 200, JSONObject()
                        .put("png_base64", data)
                        .put("mode", if (accessibilityShot != null) "device" else "browser_view"))
                }
                method == "POST" && path == "/v1/action" -> {
                    val obj = JSONObject(body)
                    val action = obj.optString("action")
                    val requestId = headers["x-hakim-request-id"]
                    if (action != "home" && (requestId == null || !REQUEST_ID.matches(requestId))) {
                        respond(c, 400, JSONObject().put("error", "request_id_required"))
                    } else if (requestId != null && !claimRequest(requestId)) {
                        respond(c, 409, JSONObject().put("error", "duplicate_request").put("request_id", requestId))
                    } else {
                        val browserScoped = obj.optString("scope") == "browser" ||
                            action.startsWith("browser_") || action in setOf("open_url", "click_text", "click_css", "scroll_by")
                        val ok = if (browserScoped) {
                            HakimBrowserController.isAttached() && HakimBrowserController.action(obj)
                        } else {
                            HakimAccessibilityService.instance?.action(obj) ?: false
                        }
                        respond(c, if (ok) 200 else 409, JSONObject()
                            .put("ok", ok)
                            .put("mode", if (browserScoped) "browser" else "accessibility")
                            .put("request_id", requestId ?: JSONObject.NULL))
                    }
                }
                method == "POST" && path == "/v1/launch" -> {
                    val requestId = headers["x-hakim-request-id"]
                    if (requestId == null || !REQUEST_ID.matches(requestId)) {
                        respond(c, 400, JSONObject().put("error", "request_id_required"))
                    } else {
                        val pkg = JSONObject(body).optString("package")
                        val valid = Regex("^[A-Za-z0-9_.]{3,200}$").matches(pkg)
                        val intent = if (valid) context.packageManager.getLaunchIntentForPackage(pkg) else null
                        if (intent == null) {
                            respond(c, 404, JSONObject().put("error", "package_not_launchable"))
                        } else if (!claimRequest(requestId)) {
                            respond(c, 409, JSONObject().put("error", "duplicate_request").put("request_id", requestId))
                        } else {
                            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            context.startActivity(intent)
                            respond(c, 200, JSONObject().put("ok", true).put("request_id", requestId))
                        }
                    }
                }
                else -> respond(c, 404, JSONObject().put("error", "not_found"))
            }
        } catch (e: Exception) { respond(c, 500, JSONObject().put("error", e.javaClass.simpleName)) }
    }

    @Synchronized
    private fun claimRequest(requestId: String): Boolean {
        val prefs = context.getSharedPreferences("hakim_idempotency", Context.MODE_PRIVATE)
        if (prefs.contains(requestId)) return false
        return prefs.edit().putLong(requestId, System.currentTimeMillis()).commit()
    }

    private fun respond(c: Socket, code: Int, json: JSONObject) {
        val bytes = json.toString().toByteArray(Charsets.UTF_8)
        val reason = if (code == 200) "OK" else "Error"
        val head = "HTTP/1.1 $code $reason\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n"
        c.getOutputStream().write(head.toByteArray(Charsets.UTF_8)); c.getOutputStream().write(bytes); c.getOutputStream().flush()
    }

    companion object {
        const val PORT = 47651
        private val REQUEST_ID = Regex("^[A-Za-z0-9._:-]{8,128}$")
    }
}
