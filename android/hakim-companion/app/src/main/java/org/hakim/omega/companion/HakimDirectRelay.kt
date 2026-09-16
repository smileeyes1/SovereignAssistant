package org.hakim.omega.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Base64
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** ناقل حكيم المستقل؛ التنفيذ محلي والناقل يرى HC1/HR1 مشفرين فقط. */
class HakimDirectRelay(private val context: Context) {
    private val executor = Executors.newSingleThreadExecutor()
    private val running = AtomicBoolean(false)

    fun start() {
        if (!running.compareAndSet(false, true)) return
        ensureApprovalChannel(context)
        executor.execute { loop() }
    }

    fun stop() { running.set(false); executor.shutdownNow() }

    private fun loop() {
        var retryMs = 2_000L
        while (running.get()) {
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val topic = prefs.getString(KEY_TOPIC, null)
            val resultTopic = prefs.getString(KEY_RESULT_TOPIC, null)
            val relayKey = prefs.getString(KEY_RELAY_KEY, null)
            val relayBase = prefs.getString(KEY_RELAY_BASE, DEFAULT_RELAY_BASE)?.trim()?.removeSuffix("/") ?: DEFAULT_RELAY_BASE
            if (topic.isNullOrBlank() || resultTopic.isNullOrBlank() || relayKey.isNullOrBlank() || !validRelayBase(relayBase)) {
                prefs.edit().putString(KEY_LAST_ERROR, "relay_not_configured").apply(); sleep(5_000L); continue
            }
            flushOutbox(context)
            val cursor = prefs.getString(KEY_LAST_MESSAGE_ID, null)
            val since = if (cursor.isNullOrBlank()) INITIAL_REPLAY_WINDOW else URLEncoder.encode(cursor, Charsets.UTF_8.name())
            try {
                val conn = URL("$relayBase/$topic/json?since=$since").openConnection() as HttpURLConnection
                conn.connectTimeout = 15_000; conn.readTimeout = 75_000; conn.requestMethod = "GET"
                conn.setRequestProperty("Accept", "application/x-ndjson")
                val code = conn.responseCode
                if (code !in 200..299) {
                    val body = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty(); conn.disconnect()
                    throw IllegalStateException("relay_http_$code:${body.take(120)}")
                }
                prefs.edit().putLong(KEY_LAST_POLL_MS, System.currentTimeMillis()).remove(KEY_LAST_ERROR).apply(); retryMs = 2_000L
                BufferedReader(InputStreamReader(conn.inputStream, Charsets.UTF_8)).use { reader ->
                    while (running.get()) {
                        val line = reader.readLine() ?: break
                        val event = runCatching { JSONObject(line) }.getOrNull() ?: continue
                        if (event.optString("event") != "message") continue
                        val id = event.optString("id").trim()
                        if (!cursor.isNullOrBlank() && id == cursor) continue
                        handleEvent(event, resultTopic, relayBase, relayKey)
                        if (id.isNotBlank()) prefs.edit().putString(KEY_LAST_MESSAGE_ID, id).apply()
                        prefs.edit().putLong(KEY_LAST_POLL_MS, System.currentTimeMillis()).apply()
                    }
                }; conn.disconnect()
            } catch (e: Exception) {
                prefs.edit().putString(KEY_LAST_ERROR, e.javaClass.simpleName + ":" + (e.message ?: "")).apply()
                flushOutbox(context); sleep(retryMs); retryMs = (retryMs * 2).coerceAtMost(60_000L)
            }
        }
    }

    private fun handleEvent(event: JSONObject, resultTopic: String, relayBase: String, relayKey: String) {
        val carrier = event.optString("message").trim(); if (carrier.length !in 32..65536) return
        val raw = decryptCarrier(carrier, relayKey) ?: return
        val envelope = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val requestId = envelope.optString("request_id"); val op = envelope.optString("op")
        val expiresAt = envelope.optLong("expires_at_ms", 0L); val payloadB64 = envelope.optString("payload_b64"); val signature = envelope.optString("signature")
        if (!REQUEST_ID.matches(requestId) || op !in ALLOWED_OPS) return
        if (payloadB64.length > MAX_PAYLOAD_B64 || !SIGNATURE.matches(signature)) return
        if (!validSignature(relayKey, requestId, op, expiresAt, payloadB64, signature)) return
        if (decodePayload(envelope) == null) { sendResult(context, resultTopic, relayBase, relayKey, requestId, "error", JSONObject().put("ok", false).put("error", "invalid_payload")); return }
        if (expiresAt <= System.currentTimeMillis()) { sendResult(context, resultTopic, relayBase, relayKey, requestId, "expired", JSONObject().put("ok", false).put("error", "request_expired")); return }
        if (!claimRemoteRequest(context, requestId)) { sendResult(context, resultTopic, relayBase, relayKey, requestId, "duplicate", JSONObject().put("ok", false).put("error", "duplicate_request")); return }
        if (op in READ_ONLY_OPS) {
            val result = executeEnvelope(context, envelope); sendResult(context, resultTopic, relayBase, relayKey, requestId, if (result.optBoolean("ok", false)) "ok" else "error", result)
        } else { savePending(context, envelope, resultTopic, relayBase); showApproval(context, requestId, op) }
    }

    private fun sleep(ms: Long) { try { Thread.sleep(ms) } catch (_: InterruptedException) { Thread.currentThread().interrupt() } }

    companion object {
        const val PREFS = "hakim"; const val KEY_TOPIC = "relay_topic"; const val KEY_RESULT_TOPIC = "relay_result_topic"
        const val KEY_RELAY_KEY = "relay_hmac_key"; const val KEY_RELAY_BASE = "relay_base_url"; const val KEY_LAST_MESSAGE_ID = "relay_last_ntfy_id"
        const val KEY_LAST_POLL_MS = "relay_last_poll_ms"; const val KEY_LAST_ERROR = "relay_last_error"; const val KEY_LAST_RESULT_ERROR = "relay_last_result_error"
        const val KEY_LAST_RESULT_SEND_MS = "relay_last_result_send_ms"
        private const val DEFAULT_RELAY_BASE = "https://ntfy.sh"; private const val INITIAL_REPLAY_WINDOW = "10m"; private const val APPROVAL_CHANNEL = "hakim_direct_approval"
        private const val ACTION_APPROVE = "org.hakim.omega.companion.DIRECT_APPROVE"; private const val ACTION_REJECT = "org.hakim.omega.companion.DIRECT_REJECT"; private const val EXTRA_REQUEST_ID = "request_id"
        private const val CARRIER_PREFIX = "HC1."; private const val CARRIER_AAD = "HAKIM-CARRIER-v1"; private const val RESULT_PREFIX = "HR1."; private const val RESULT_AAD = "HAKIM-RESULT-v1"
        private const val GCM_NONCE_BYTES = 12; private const val GCM_TAG_BITS = 128; private const val MAX_PAYLOAD_B64 = 32768; private const val OUTBOX_PREFS = "hakim_direct_outbox"
        private val REQUEST_ID = Regex("^[A-Za-z0-9._:-]{8,128}$"); private val SIGNATURE = Regex("^[0-9a-fA-F]{64}$"); private val RELAY_KEY = Regex("^[A-Za-z0-9_-]{40,100}$"); private val TOPIC = Regex("^[A-Za-z0-9_-]{20,120}$")
        private val READ_ONLY_OPS = setOf("status", "ui", "notifications", "screenshot"); private val ALLOWED_OPS = READ_ONLY_OPS + setOf("action", "launch")

        fun configure(context: Context, topic: String?, resultTopic: String?, relayKey: String?, relayBase: String? = DEFAULT_RELAY_BASE): Boolean {
            val base = relayBase?.trim()?.removeSuffix("/") ?: DEFAULT_RELAY_BASE
            if (topic.isNullOrBlank() || !TOPIC.matches(topic) || resultTopic.isNullOrBlank() || !TOPIC.matches(resultTopic) || relayKey.isNullOrBlank() || !RELAY_KEY.matches(relayKey) || !validRelayBase(base)) return false
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_TOPIC, topic).putString(KEY_RESULT_TOPIC, resultTopic).putString(KEY_RELAY_KEY, relayKey).putString(KEY_RELAY_BASE, base).remove(KEY_LAST_MESSAGE_ID).remove(KEY_LAST_ERROR).apply(); return true
        }
        fun isConfigured(context: Context): Boolean { val p=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE); return !p.getString(KEY_TOPIC,null).isNullOrBlank()&&!p.getString(KEY_RESULT_TOPIC,null).isNullOrBlank()&&!p.getString(KEY_RELAY_KEY,null).isNullOrBlank()&&validRelayBase(p.getString(KEY_RELAY_BASE,DEFAULT_RELAY_BASE)?:DEFAULT_RELAY_BASE) }
        private fun validRelayBase(value:String)=Regex("^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%-]+)*$").matches(value)
        private fun decryptCarrier(carrier:String,relayKey:String):String? { if(!carrier.startsWith(CARRIER_PREFIX))return null; val packed=runCatching{Base64.decode(carrier.removePrefix(CARRIER_PREFIX),Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)}.getOrNull()?:return null; if(packed.size<GCM_NONCE_BYTES+16)return null; val nonce=packed.copyOfRange(0,GCM_NONCE_BYTES); val ciphertext=packed.copyOfRange(GCM_NONCE_BYTES,packed.size); return runCatching{val aesKey=MessageDigest.getInstance("SHA-256").digest("$CARRIER_AAD\u0000$relayKey".toByteArray()); val cipher=Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE,SecretKeySpec(aesKey,"AES"),GCMParameterSpec(GCM_TAG_BITS,nonce)); cipher.updateAAD(CARRIER_AAD.toByteArray()); String(cipher.doFinal(ciphertext),Charsets.UTF_8)}.getOrNull() }
        private fun validSignature(relayKey:String,requestId:String,op:String,expiresAt:Long,payloadB64:String,signature:String):Boolean { val canonical="$requestId\n$op\n$expiresAt\n$payloadB64"; val mac=Mac.getInstance("HmacSHA256"); mac.init(SecretKeySpec(relayKey.toByteArray(),"HmacSHA256")); val expected=mac.doFinal(canonical.toByteArray()).joinToString(""){"%02x".format(it.toInt() and 0xff)}; return MessageDigest.isEqual(expected.toByteArray(Charsets.US_ASCII),signature.lowercase().toByteArray(Charsets.US_ASCII)) }
        private fun claimRemoteRequest(context:Context,requestId:String):Boolean { val prefs=context.getSharedPreferences("hakim_direct_idempotency",Context.MODE_PRIVATE); if(prefs.contains(requestId))return false; return prefs.edit().putLong(requestId,System.currentTimeMillis()).commit() }
        private fun savePending(context:Context,envelope:JSONObject,resultTopic:String,relayBase:String){val id=envelope.optString("request_id"); context.getSharedPreferences("hakim_direct_pending",Context.MODE_PRIVATE).edit().putString("$id.envelope",envelope.toString()).putString("$id.result_topic",resultTopic).putString("$id.relay_base",relayBase).commit()}
        private data class Pending(val envelope:JSONObject,val resultTopic:String,val relayBase:String)
        private fun readPending(context:Context,requestId:String):Pending?{val p=context.getSharedPreferences("hakim_direct_pending",Context.MODE_PRIVATE); val raw=p.getString("$requestId.envelope",null)?:return null; val topic=p.getString("$requestId.result_topic",null)?:return null; val base=p.getString("$requestId.relay_base",null)?:return null; return runCatching{Pending(JSONObject(raw),topic,base)}.getOrNull()}
        private fun clearPending(context:Context,requestId:String){context.getSharedPreferences("hakim_direct_pending",Context.MODE_PRIVATE).edit().remove("$requestId.envelope").remove("$requestId.result_topic").remove("$requestId.relay_base").remove("$requestId.relay_key").commit()}
        private fun currentRelayKey(context:Context):String?=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_RELAY_KEY,null)?.takeIf{RELAY_KEY.matches(it)}
        private fun showApproval(context:Context,requestId:String,op:String){ensureApprovalChannel(context); val approve=PendingIntent.getBroadcast(context,requestId.hashCode(),Intent(context,DirectApprovalReceiver::class.java).setAction(ACTION_APPROVE).putExtra(EXTRA_REQUEST_ID,requestId),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE); val reject=PendingIntent.getBroadcast(context,requestId.hashCode() xor 0x55AA,Intent(context,DirectApprovalReceiver::class.java).setAction(ACTION_REJECT).putExtra(EXTRA_REQUEST_ID,requestId),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE); val n=android.app.Notification.Builder(context,APPROVAL_CHANNEL).setContentTitle("حكيم — موافقة مطلوبة").setContentText("طلب تغيير على الهاتف: $op").setSmallIcon(android.R.drawable.ic_lock_lock).setAutoCancel(true).addAction(android.R.drawable.ic_input_add,"موافقة",approve).addAction(android.R.drawable.ic_delete,"رفض",reject).build(); context.getSystemService(NotificationManager::class.java).notify(requestId.hashCode(),n)}
        fun handleApproval(context:Context,requestId:String,approved:Boolean){val pending=readPending(context,requestId)?:return; val relayKey=currentRelayKey(context)?:return; if(!approved){sendResult(context,pending.resultTopic,pending.relayBase,relayKey,requestId,"rejected",JSONObject().put("ok",false).put("error","rejected_by_user")); clearPending(context,requestId); return}; if(pending.envelope.optLong("expires_at_ms",0L)<=System.currentTimeMillis()){sendResult(context,pending.resultTopic,pending.relayBase,relayKey,requestId,"expired",JSONObject().put("ok",false).put("error","request_expired")); clearPending(context,requestId); return}; Executors.newSingleThreadExecutor().execute{val result=executeEnvelope(context,pending.envelope); sendResult(context,pending.resultTopic,pending.relayBase,relayKey,requestId,if(result.optBoolean("ok",false))"ok" else "error",result); clearPending(context,requestId)}}
        private fun decodePayload(envelope:JSONObject):JSONObject?{val b=envelope.optString("payload_b64"); if(b.isBlank())return JSONObject(); return runCatching{JSONObject(String(Base64.decode(b,Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING),Charsets.UTF_8))}.getOrNull()}
        private fun executeEnvelope(context:Context,envelope:JSONObject):JSONObject{val id=envelope.optString("request_id"); val p=decodePayload(envelope)?:return JSONObject().put("ok",false).put("error","invalid_payload"); return when(envelope.optString("op")){"status"->localRequest(context,"GET","/v1/status",null,null);"ui"->localRequest(context,"GET","/v1/ui",null,null);"notifications"->localRequest(context,"GET","/v1/notifications",null,null);"screenshot"->localRequest(context,"GET","/v1/screenshot",null,null);"action"->localRequest(context,"POST","/v1/action",p,id);"launch"->localRequest(context,"POST","/v1/launch",p,id);else->JSONObject().put("ok",false).put("error","unsupported_operation")}}
        private fun localRequest(context:Context,method:String,path:String,body:JSONObject?,requestId:String?):JSONObject{val token=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("pair_token",null)?:return JSONObject().put("ok",false).put("error","not_paired"); return try{val c=URL("http://127.0.0.1:${LocalControlServer.PORT}$path").openConnection() as HttpURLConnection;c.connectTimeout=4000;c.readTimeout=20000;c.requestMethod=method;c.setRequestProperty("Authorization","Bearer $token");if(requestId!=null)c.setRequestProperty("X-HAKIM-Request-ID",requestId);if(body!=null){c.doOutput=true;c.setRequestProperty("Content-Type","application/json; charset=utf-8");c.outputStream.use{it.write(body.toString().toByteArray())}};val code=c.responseCode;val stream=if(code in 200..299)c.inputStream else c.errorStream;val text=stream?.bufferedReader(Charsets.UTF_8)?.use{it.readText()}.orEmpty();c.disconnect();runCatching{JSONObject(text)}.getOrElse{JSONObject().put("raw",text)}.put("ok",code in 200..299)}catch(e:Exception){JSONObject().put("ok",false).put("error",e.javaClass.simpleName)}}
        private fun encryptResult(raw:String,relayKey:String):String{val nonce=ByteArray(GCM_NONCE_BYTES).also{SecureRandom().nextBytes(it)};val aesKey=MessageDigest.getInstance("SHA-256").digest("$RESULT_AAD\u0000$relayKey".toByteArray());val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,SecretKeySpec(aesKey,"AES"),GCMParameterSpec(GCM_TAG_BITS,nonce));cipher.updateAAD(RESULT_AAD.toByteArray());val packed=nonce+cipher.doFinal(raw.toByteArray());return RESULT_PREFIX+Base64.encodeToString(packed,Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)}
        private fun outboxKey(requestId:String,status:String)=MessageDigest.getInstance("SHA-256").digest("$requestId\n$status".toByteArray()).joinToString(""){"%02x".format(it.toInt() and 0xff)}
        private fun queueResult(context:Context,resultTopic:String,relayBase:String,relayKey:String,requestId:String,status:String,result:JSONObject):String{val key=outboxKey(requestId,status);val raw=JSONObject().put("request_id",requestId).put("status",status).put("received_at_ms",System.currentTimeMillis()).put("result",result).toString();val item=JSONObject().put("topic",resultTopic).put("base",relayBase).put("carrier",encryptResult(raw,relayKey)).put("attempts",0).put("next_attempt_ms",0L);context.getSharedPreferences(OUTBOX_PREFS,Context.MODE_PRIVATE).edit().putString(key,item.toString()).commit();return key}
        private fun postQueuedResult(context:Context,key:String,item:JSONObject):Boolean{val now=System.currentTimeMillis();if(item.optLong("next_attempt_ms",0L)>now)return false;return try{val c=URL("${item.getString("base")}/${item.getString("topic")}").openConnection() as HttpURLConnection;c.connectTimeout=10000;c.readTimeout=20000;c.requestMethod="POST";c.doOutput=true;c.setRequestProperty("Content-Type","text/plain; charset=utf-8");c.outputStream.use{it.write(item.getString("carrier").toByteArray())};val code=c.responseCode;runCatching{c.inputStream?.close()};c.disconnect();if(code !in 200..299)throw IllegalStateException("result_http_$code");context.getSharedPreferences(OUTBOX_PREFS,Context.MODE_PRIVATE).edit().remove(key).commit();context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putLong(KEY_LAST_RESULT_SEND_MS,now).remove(KEY_LAST_RESULT_ERROR).apply();true}catch(e:Exception){val attempts=item.optInt("attempts",0)+1;val delay=(2000L shl attempts.coerceAtMost(5)).coerceAtMost(60000L);item.put("attempts",attempts).put("next_attempt_ms",now+delay);context.getSharedPreferences(OUTBOX_PREFS,Context.MODE_PRIVATE).edit().putString(key,item.toString()).commit();context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_LAST_RESULT_ERROR,e.javaClass.simpleName+":"+(e.message?:"")).apply();false}}
        private fun flushOutbox(context:Context){val p=context.getSharedPreferences(OUTBOX_PREFS,Context.MODE_PRIVATE);p.all.toMap().forEach{(key,value)->val raw=value as? String?:return@forEach;val item=runCatching{JSONObject(raw)}.getOrNull()?:return@forEach;postQueuedResult(context,key,item)}}
        private fun sendResult(context:Context,resultTopic:String,relayBase:String,relayKey:String,requestId:String,status:String,result:JSONObject){val key=queueResult(context,resultTopic,relayBase,relayKey,requestId,status,result);val raw=context.getSharedPreferences(OUTBOX_PREFS,Context.MODE_PRIVATE).getString(key,null)?:return;runCatching{JSONObject(raw)}.getOrNull()?.let{postQueuedResult(context,key,it)}}
        private fun ensureApprovalChannel(context:Context){if(Build.VERSION.SDK_INT>=26)context.getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(APPROVAL_CHANNEL,"موافقات حكيم المستقلة",NotificationManager.IMPORTANCE_HIGH))}
    }
}
class DirectApprovalReceiver:BroadcastReceiver(){override fun onReceive(context:Context,intent:Intent){val requestId=intent.getStringExtra("request_id")?:return;when(intent.action){"org.hakim.omega.companion.DIRECT_APPROVE"->HakimDirectRelay.handleApproval(context,requestId,true);"org.hakim.omega.companion.DIRECT_REJECT"->HakimDirectRelay.handleApproval(context,requestId,false)}}}
