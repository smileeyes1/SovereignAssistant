package org.hakim.omega.companion

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import io.github.muntashirakon.adb.AbsAdbConnectionManager
import io.github.muntashirakon.adb.android.AdbMdns
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.cert.Certificate
import java.util.Date
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.security.auth.x500.X500Principal

/**
 * ADB client owned by HAKIM itself.
 *
 * The private key never leaves AndroidKeyStore. Pairing and connection are local to
 * the phone and use Android's Wireless Debugging daemon over loopback/local mDNS.
 */
class HakimAdbConnectionManager private constructor(context: Context) : AbsAdbConnectionManager() {
    data class PairResult(
        val paired: Boolean,
        val connected: Boolean,
        val host: String?,
        val pairingPort: Int?,
        val error: String? = null,
    )

    private val privateKey: PrivateKey
    private val certificate: Certificate

    init {
        setApi(Build.VERSION.SDK_INT)
        setHostAddress("127.0.0.1")
        setTimeout(15, TimeUnit.SECONDS)

        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val now = System.currentTimeMillis()
            val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore")
            generator.initialize(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
                )
                    .setKeySize(2048)
                    .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA512)
                    .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
                    .setCertificateSubject(X500Principal("CN=HAKIM Local ADB"))
                    .setCertificateSerialNumber(BigInteger.ONE)
                    .setCertificateNotBefore(Date(now - 86_400_000L))
                    .setCertificateNotAfter(Date(now + TEN_YEARS_MS))
                    .setUserAuthenticationRequired(false)
                    .build()
            )
            generator.generateKeyPair()
        }

        privateKey = keyStore.getKey(KEY_ALIAS, null) as PrivateKey
        certificate = keyStore.getCertificate(KEY_ALIAS)
    }

    override fun getPrivateKey(): PrivateKey = privateKey
    override fun getCertificate(): Certificate = certificate
    override fun getDeviceName(): String = "HAKIM-${Build.MODEL}"

    fun pairAndConnect(context: Context, pairingCode: String, timeoutMillis: Long = 30_000L): PairResult {
        if (!pairingCode.matches(Regex("^[0-9]{6}$"))) {
            return PairResult(false, false, null, null, "INVALID_PAIRING_CODE")
        }

        val latch = CountDownLatch(1)
        var host: String? = null
        var port = -1
        val mdns = AdbMdns(context.applicationContext, AdbMdns.SERVICE_TYPE_TLS_PAIRING) { address, discoveredPort ->
            if (address != null && discoveredPort > 0 && port <= 0) {
                host = address.hostAddress
                port = discoveredPort
                latch.countDown()
            }
        }

        return try {
            mdns.start()
            if (!latch.await(timeoutMillis, TimeUnit.MILLISECONDS)) {
                PairResult(false, false, null, null, "PAIRING_SERVICE_NOT_FOUND")
            } else {
                val resolvedHost = host ?: "127.0.0.1"
                pair(resolvedHost, port, pairingCode)
                runCatching { disconnect() }
                val connected = autoConnect(context.applicationContext, 20_000L) || isConnected
                PairResult(true, connected, resolvedHost, port, if (connected) null else "PAIRED_BUT_CONNECT_FAILED")
            }
        } catch (t: Throwable) {
            PairResult(false, false, host, port.takeIf { it > 0 }, t.javaClass.simpleName + ":" + (t.message ?: "unknown"))
        } finally {
            runCatching { mdns.stop() }
        }
    }

    companion object {
        private const val KEY_ALIAS = "hakim_native_local_adb_v1"
        private const val TEN_YEARS_MS = 3650L * 24L * 60L * 60L * 1000L
        @Volatile private var instance: HakimAdbConnectionManager? = null

        fun get(context: Context): HakimAdbConnectionManager =
            instance ?: synchronized(this) {
                instance ?: HakimAdbConnectionManager(context.applicationContext).also { instance = it }
            }
    }
}
