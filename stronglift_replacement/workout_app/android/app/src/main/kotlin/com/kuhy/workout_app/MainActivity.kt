package com.kuhy.workout_app

import android.content.Intent
import android.os.Bundle
import android.util.Log
import com.pravera.flutter_foreground_task.service.ForegroundService
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        relayNotificationPress(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        relayNotificationPress(intent)
    }

    // flutter_foreground_task only tells the service a notification was tapped
    // when the opening intent is MAIN + LAUNCHER. The sandbox flavor has no
    // LAUNCHER filter (it must stay out of the launcher), so its press would
    // be dropped and the run notification could never open the finish modal.
    // Hand such a press to the plugin as if it were a LAUNCHER intent. A real
    // LAUNCHER intent was already handled by the plugin: not relayed twice.
    private fun relayNotificationPress(opened: Intent?) {
        if (opened == null ||
            opened.getStringExtra(PRESS_EXTRA) != PRESS_ACTION ||
            opened.hasCategory(Intent.CATEGORY_LAUNCHER)
        ) {
            return
        }
        Log.i(LOG_TAG, "notification press relayed")
        ForegroundService.handleNotificationContentIntent(
            Intent(opened).addCategory(Intent.CATEGORY_LAUNCHER),
        )
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // The sandbox flavor is a build-time fact; Dart asks for it once at
        // startup rather than carrying a second --dart-define switch that
        // could disagree with the package name. The same channel carries the
        // sandbox trace to logcat under its own tag, so
        // `adb logcat -s WorkoutSandbox` shows nothing but the trace.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "isSandbox" -> result.success(BuildConfig.FLAVOR == "sandbox")
                    // A slot build runs this code under another package name;
                    // Dart keys its /sdcard paths on it.
                    "packageName" -> result.success(applicationContext.packageName)
                    "log" -> {
                        Log.i(LOG_TAG, call.arguments as String)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
        // Hands a key parked by PairPcReceiver to Dart, which stores it in
        // secure storage and only then asks for the parked copy to go.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, PAIRING_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "takePending" -> try {
                        result.success(PairPcReceiver.takePending(applicationContext))
                    } catch (error: Exception) {
                        result.error("pairing_unreadable", error.toString(), null)
                    }
                    "clearPending" -> {
                        PairPcReceiver.clearPending(applicationContext)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    companion object {
        const val PAIRING_CHANNEL = "com.kuhy.workout_app/pc_pairing"
        const val CHANNEL = "com.kuhy.workout_app/sandbox"
        const val LOG_TAG = "WorkoutSandbox"

        // The extra the plugin puts on its notification's launch intent.
        private const val PRESS_EXTRA = "intentData"
        private const val PRESS_ACTION = "onNotificationPressed"
    }
}
