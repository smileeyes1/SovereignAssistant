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
        if (socket != null) return
        pool.execute {
            try {
                val s = ServerSocket()
                s.reuseAddress = true
                s.bind(InetSocketAddress(InetAddress.getLoopbackAddress(), PORT))
                socket = s
                while (!s.isClosed) runCatching { s.accept() }.getOrNull()?.let { client -> pool.execute { handle(client) } }
            } catch (_: Exception) {}
        }
    }

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
            route(c, method, path, body)
        }
    }

    private fun route(c: Socket, method: String, path: String, body: String) {
        try {
            when {
                method == "GET" && path == "/v1/status" -> respond(c, 200, JSONObject()
                    .put("status", "PASS")
                    .put("loopback_only", true)
                    .put("accessibility", HakimAccessibilityService.instance != null)
                    .put("notifications_buffered", HakimNotificationListener.snapshot().length()))
                method == "GET" && path == "/v1/ui" -> respond(c, 200, JSONObject().put("nodes", HakimAccessibilityService.instance?.uiSnapshot() ?: org.json.JSONArray()))
                method == "GET" && path == "/v1/notifications" -> respond(c, 200, JSONObject().put("items", HakimNotificationListener.snapshot()))
                method == "GET" && path == "/v1/screenshot" -> {
                    val data = HakimAccessibilityService.instance?.screenshotBase64()
                    if (data == null) respond(c, 409, JSONObject().put("error", "screenshot_unavailable"))
                    else respond(c, 200, JSONObject().put("png_base64", data))
                }
                method == "POST" && path == "/v1/action" -> {
                    val ok = HakimAccessibilityService.instance?.action(JSONObject(body)) == true
                    respond(c, if (ok) 200 else 409, JSONObject().put("ok", ok))
                }
                method == "POST" && path == "/v1/launch" -> {
                    val pkg = JSONObject(body).optString("package")
                    val valid = Regex("^[A-Za-z0-9_.]{3,200}$").matches(pkg)
                    val intent = if (valid) context.packageManager.getLaunchIntentForPackage(pkg) else null
                    if (intent == null) respond(c, 404, JSONObject().put("error", "package_not_launchable"))
                    else { intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); context.startActivity(intent); respond(c, 200, JSONObject().put("ok", true)) }
                }
                else -> respond(c, 404, JSONObject().put("error", "not_found"))
            }
        } catch (e: Exception) { respond(c, 500, JSONObject().put("error", e.javaClass.simpleName)) }
    }

    private fun respond(c: Socket, code: Int, json: JSONObject) {
        val bytes = json.toString().toByteArray(Charsets.UTF_8)
        val reason = if (code == 200) "OK" else "Error"
        val head = "HTTP/1.1 $code $reason\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n"
        c.getOutputStream().write(head.toByteArray(Charsets.UTF_8)); c.getOutputStream().write(bytes); c.getOutputStream().flush()
    }

    companion object { const val PORT = 47651 }
}
