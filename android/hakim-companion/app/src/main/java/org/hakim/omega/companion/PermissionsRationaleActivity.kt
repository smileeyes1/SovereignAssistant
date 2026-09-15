package org.hakim.omega.companion

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

class PermissionsRationaleActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(32, 42, 32, 32)
        }
        root.addView(TextView(this).apply {
            text = "خصوصية الصحة في حكيم"
            textSize = 24f
        })
        root.addView(TextView(this).apply {
            text = "يطلب حكيم في هذه المرحلة إذن قراءة النبض والخطوات فقط عبر Health Connect. " +
                "تُعرض القراءة محليًا للمستخدم ولا تُكتب بيانات صحية إلى Health Connect ولا تُرفع إلى مستودع عام. " +
                "يمكن سحب الإذن في أي وقت من إعدادات Health Connect. " +
                "هذه البيانات للاستفادة المعلوماتية وليست تشخيصًا طبيًا، ولا تمنح حكيم سلطة على أي جهاز طبي مزروع أو علاج."
            textSize = 16f
            setPadding(0, 28, 0, 0)
        })
        setContentView(root)
    }
}
