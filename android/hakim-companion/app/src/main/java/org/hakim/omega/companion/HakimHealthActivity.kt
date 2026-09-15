package org.hakim.omega.companion

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

    private val requestPermissionsLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status.text = if (granted.containsAll(HakimHealthConnectBridge.readPermissions)) {
            "تم منح إذن القراءة. يمكنك الآن قراءة ملخص آخر ٢٤ ساعة."
        } else {
            "لم تُمنح كل الأذونات. لا يقرأ حكيم البيانات الصحية دون موافقتك."
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
            text = "حكيم — القلب والصحة"
            textSize = 24f
        })
        root.addView(TextView(this).apply {
            text = "قراءة محلية فقط في المرحلة الحالية: النبض والخطوات من Health Connect. لا كتابة، لا تشخيص، ولا تحكم بجهاز طبي."
            textSize = 15f
            setPadding(0, 16, 0, 16)
        })

        status = TextView(this).apply {
            textSize = 15f
            setPadding(0, 10, 0, 18)
        }
        root.addView(status, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        root.addView(Button(this).apply {
            text = "منح إذن قراءة النبض والخطوات"
            setOnClickListener {
                if (HakimHealthConnectBridge.availability(this@HakimHealthActivity) == HealthConnectClient.SDK_AVAILABLE) {
                    requestPermissionsLauncher.launch(HakimHealthConnectBridge.readPermissions)
                } else {
                    status.text = "Health Connect ${HakimHealthConnectBridge.availabilityText(this@HakimHealthActivity)}"
                }
            }
        })

        root.addView(Button(this).apply {
            text = "قراءة آخر ٢٤ ساعة"
            setOnClickListener { readSummary() }
        })

        root.addView(Button(this).apply {
            text = "إغلاق"
            setOnClickListener { finish() }
        })

        setContentView(root)
        lifecycleScope.launch {
            status.text = when {
                HakimHealthConnectBridge.availability(this@HakimHealthActivity) != HealthConnectClient.SDK_AVAILABLE ->
                    "Health Connect ${HakimHealthConnectBridge.availabilityText(this@HakimHealthActivity)}"
                HakimHealthConnectBridge.hasReadPermissions(this@HakimHealthActivity) ->
                    "Health Connect متاح وأذونات القراءة ممنوحة."
                else -> "Health Connect متاح، ولم تُمنح أذونات القراءة بعد."
            }
        }
    }

    private fun readSummary() {
        lifecycleScope.launch {
            status.text = "جارٍ قراءة البيانات محليًا..."
            val result = runCatching { HakimHealthConnectBridge.readLast24Hours(this@HakimHealthActivity) }
            status.text = result.fold(
                onSuccess = { HakimHealthConnectBridge.humanSummary(it) },
                onFailure = { "تعذرت القراءة بأمان: ${it.message ?: "خطأ غير محدد"}" }
            )
        }
    }
}
