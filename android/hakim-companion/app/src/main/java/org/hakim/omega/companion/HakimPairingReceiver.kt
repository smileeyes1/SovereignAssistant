package org.hakim.omega.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.RemoteInput

class HakimPairingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != HakimLocalPairing.ACTION_SUBMIT_PAIRING_CODE) return
        val results = RemoteInput.getResultsFromIntent(intent) ?: return
        val code = results.getCharSequence(HakimLocalPairing.REMOTE_INPUT_CODE)?.toString().orEmpty()
        HakimLocalPairing.submitCode(context.applicationContext, code)
    }
}
