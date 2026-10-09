package com.kuhy.workout_app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Process
import android.util.Log
import org.json.JSONObject
import java.io.File

/**
 * Pairs this install with the PC for the workout poke, over adb only.
 *
 * `scripts/pair_phone.sh` on the PC runs
 * `adb shell am broadcast -a com.kuhy.workout_app.PAIR_PC -n <pkg>/com.kuhy.workout_app.PairPcReceiver --es key <64 hex> [--es host <ip>]`.
 *
 * Two gates keep anything but the adb shell out:
 *  - the manifest requires the sender to hold `android.permission.DUMP`,
 *    which the shell has and no third-party app can be granted;
 *  - on API >= 34 the sender uid, when the platform shares it, must be the
 *    shell (2000) or root (0).
 *
 * A manifest receiver runs without a Dart isolate, so the key is parked in
 * a private no-backup file; Dart moves it into secure storage the next time
 * it asks (`PcPairing.absorbPending`) and only then deletes the file.
 * The result code/data are what `am broadcast` prints and what
 * `scripts/pair_phone.sh` parses: `result=-1 data="paired"` on success,
 * `result=0 data="<reason>"` on rejection. `result=0` with NO data means the
 * receiver never ran (sender lacks DUMP, or the OEM blocked a stopped app).
 * An omitted host keeps the current setting.
 */
class PairPcReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return refuse("unexpected action ${intent.action}")
        if (Build.VERSION.SDK_INT >= 34) {
            val uid = sentFromUid
            Log.i(TAG, "pair request sentFromUid=$uid")
            if (uid != Process.INVALID_UID && uid != SHELL_UID && uid != ROOT_UID) {
                return refuse("sender uid $uid is not the adb shell")
            }
        }
        val key = intent.getStringExtra("key")?.trim()?.lowercase()
        if (key == null || !KEY_PATTERN.matches(key)) {
            return refuse("key must be exactly 64 hex characters")
        }
        val host = intent.getStringExtra("host")?.trim()
        if (host != null && !HOST_PATTERN.matches(host)) {
            return refuse("host '$host' is not an IPv4 address or hostname")
        }
        val json = JSONObject().put("key", key)
        if (host != null) json.put("host", host)
        try {
            pendingFile(context).writeText(json.toString())
        } catch (error: Exception) {
            return refuse("could not park the key: $error")
        }
        Log.i(TAG, "pairing parked for ${context.packageName}; the app absorbs it on next use")
        setResult(RESULT_PAIRED, "paired", null)
    }

    private fun refuse(reason: String) {
        Log.w(TAG, "pairing refused: $reason")
        setResult(RESULT_REFUSED, reason, null)
    }

    companion object {
        const val ACTION = "com.kuhy.workout_app.PAIR_PC"
        const val TAG = "WorkoutPair"
        const val RESULT_PAIRED = -1 // Activity.RESULT_OK
        const val RESULT_REFUSED = 0 // Activity.RESULT_CANCELED
        private const val SHELL_UID = 2000
        private const val ROOT_UID = 0
        private val KEY_PATTERN = Regex("^[0-9a-f]{64}$")
        private val HOST_PATTERN = Regex("^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")

        fun pendingFile(context: Context): File =
            File(context.noBackupFilesDir, "pc_pairing_pending.json")

        /** `{key, host?}` parked by [onReceive], or null. */
        fun takePending(context: Context): Map<String, String>? {
            val file = pendingFile(context)
            if (!file.exists()) return null
            val json = JSONObject(file.readText())
            val out = mutableMapOf("key" to json.getString("key"))
            if (json.has("host")) out["host"] = json.getString("host")
            return out
        }

        fun clearPending(context: Context) {
            pendingFile(context).delete()
        }
    }
}
