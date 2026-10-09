package com.kuhy.workout_app

import android.util.Log
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
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
    }
}
