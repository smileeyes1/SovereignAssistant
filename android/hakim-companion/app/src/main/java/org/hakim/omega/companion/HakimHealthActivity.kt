package org.hakim.omega.companion

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class HakimHealthActivity : ComponentActivity() {
    private lateinit var status: TextView
    private lateinit var revokeButton: Button
    private var firstResume = true

    private val requestPermissionsLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(HakimHealthConnectBridge.readPermissions)) {
            HakimHealthFieldQualification.markPermissionGranted(this)
            runReadQualification()
        } else {
            status.text = "لم تُمنح كل الأذونات. بقي حكيم مغلقًا عن البيانات الصحية."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(28, 36, 28, 28)
        }
        root.addView(TextView(this).apply {
            text = "حكيم — تأهيل القلب والصحة"
            textSize = 24f
        })
        root.addView(TextView(this).apply {
            text = "مسار محلي مقفول: قراءة النبض والخطوات فقط. لا كتابة، لا تشخيص، لا تحكم بجهاز طبي، ولا حفظ لقيم النبض داخل سجل التأهيل."
            textSize = 15f
            setPadding(0, 16, 0, 16)
        })

        status = TextView(this).apply {
            textSize = 15f
            setPadding(0, 10, 0, 18)
        }
        root.addView(status, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        root.addView(Button(this).apply {
            text = "تأهيل القلب والصحة تلقائيًا"
            setOnClickListener { startQualification() }
        })

        revokeButton = Button(this).apply {
            text = "اختبار سحب الإذن — الخطوة النهائية"
            setOnClickListener { openRevocationTest() }
        }
        root.addView(revokeButton)

        root.addView(Button(this).apply {
            text = "إعادة اختبار الصحة من البداية"
            setOnClickListener {
                HakimHealthFieldQualification.reset(this@HakimHealthActivity)
                refreshQualificationState()
            }
        })

        root.addView(Button(this).apply {
            text = "إغلاق"
            setOnClickListener { finish() }
        })

        setContentView(root)
        refreshQualificationState()
    }

    override fun onResume() {
        super.onResume()
        if (firstResume) {
            firstResume = false
            return
        }
        if (!::status.isInitialized) return
        lifecycleScope.launch {
            if (HakimHealthFieldQualification.awaitingRevocation(this@HakimHealthActivity) &&
                HakimHealthConnectBridge.availability(this@HakimHealthActivity) == HealthConnectClient.SDK_AVAILABLE &&
                !HakimHealthConnectBridge.hasReadPermissions(this@HakimHealthActivity)
            ) {
                val denied = runCatching { HakimHealthConnectBridge.readLast24Hours(this@HakimHealthActivity) }.isFailure
                if (denied) HakimHealthFieldQualification.markRevocationProven(this@HakimHealthActivity)
            }
            refreshQualificationState()
        }
    }

    private fun startQualification() {
        lifecycleScope.launch {
            when {
                HakimHealthConnectBridge.availability(this@HakimHealthActivity) != HealthConnectClient.SDK_AVAILABLE ->
                    status.text = "Health Connect ${HakimHealthConnectBridge.availabilityText(this@HakimHealthActivity)}. لا توجد ترقية زائفة."
                !HakimHealthConnectBridge.hasReadPermissions(this@HakimHealthActivity) -> {
                    status.text = "يلزم إذن Android المحلي للنبض والخطوات."
                    requestPermissionsLauncher.launch(HakimHealthConnectBridge.readPermissions)
                }
                else -> runReadQualification()
            }
        }
    }

    private fun runReadQualification() {
        lifecycleScope.launch {
            status.text = "جارٍ اختبار القراءة محليًا..."
            val result = runCatching { HakimHealthConnectBridge.readLast24Hours(this@HakimHealthActivity) }
            result.onSuccess {
                HakimHealthFieldQualification.markReadSuccess(this@HakimHealthActivity, it)
                status.text = HakimHealthConnectBridge.humanSummary(it) +
                    "\n\nنجحت بوابة القراءة. بقي اختبار واحد فقط: سحب الإذن ثم العودة إلى حكيم."
            }.onFailure {
                status.text = "فشل الاختبار مغلقًا: ${it.message ?: "سبب غير محدد"}"
            }
            refreshRevokeButton()
        }
    }

    private fun openRevocationTest() {
        if (!HakimHealthFieldQualification.readProven(this)) {
            status.text = "أكمل اختبار القراءة أولًا."
            return
        }
        HakimHealthFieldQualification.beginRevocationTest(this)
        status.text = "في Health Connect أوقف إذن حكيم للنبض والخطوات، ثم ارجع إلى حكيم. سيختبر الإغلاق تلقائيًا."
        runCatching { startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS)) }
            .onFailure { status.text = "تعذر فتح إعدادات Health Connect: ${it.message ?: "خطأ"}" }
    }

    private fun refreshQualificationState() {
        lifecycleScope.launch {
            val hc = HakimHealthConnectBridge.availabilityText(this@HakimHealthActivity)
            status.text = if (HakimHealthFieldQualification.healthGateReady(this@HakimHealthActivity)) {
                "بوابة القلب والصحة مؤهلة محليًا: القراءة مثبتة وسحب الإذن يفشل مغلقًا.\n" +
                    HakimHealthFieldQualification.summary(this@HakimHealthActivity)
            } else {
                "Health Connect: $hc\n" + HakimHealthFieldQualification.summary(this@HakimHealthActivity)
            }
            refreshRevokeButton()
        }
    }

    private fun refreshRevokeButton() {
        if (::revokeButton.isInitialized) {
            revokeButton.isEnabled = HakimHealthFieldQualification.readProven(this) &&
                !HakimHealthFieldQualification.revocationProven(this)
        }
    }
}
