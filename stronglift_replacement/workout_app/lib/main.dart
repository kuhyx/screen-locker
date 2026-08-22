
import 'dart:async';
import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/lock_mode.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_device_id.dart';
import 'package:workout_app/ui/theme.dart';

// coverage:ignore-start
// App bootstrap: permission request, DB init, and a real listening socket —
// platform-channel work that can't run on the CI test host. The pieces it wires
// up are unit-tested individually; the entry point itself is not.
void main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  // Must precede runApp: the UI reads this to decide whether to offer
  // any way out of the workout.
  lockModeEnabled = parseLockMode(args);
  // Linux desktop has no sqflite plugin. The FFI factory runs the same
  // schema and migrations against the same SQL, so this is a transport
  // swap, not a second storage implementation. Must precede any DB open.
  if (Platform.isLinux) {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  }
  // Before anything that stamps an Hlc or syncs: until this resolves, the
  // device id falls back to the pre-migration constant.
  await initSyncDeviceId();
  // Storage permission is settled before the DB is opened: opening it seeds
  // factory defaults for any missing exercise, and restoring afterwards is a
  // no-op once rows exist. Losing that race is what wiped months of
  // progression on 2026-08-05.
  //
  // CHECKED, never requested. `request()` throws the user into a system
  // Settings page on every launch where the permission is absent, and since
  // Firebase now carries progression the `/sdcard` backup is a second copy
  // rather than the only one. The grant prompt lives in Settings, where the
  // user asks for it.
  final storageGranted = await BackupService.instance.hasStoragePermission();
  if (!storageGranted) {
    debugPrint(
      'WorkoutApp: no storage permission — the backup at $kBackupPath can '
      'neither be read nor written, so progression rides on Firebase alone. '
      'Grant it in Settings to keep a second, offline copy.',
    );
  }
  await StorageService.init();
  await StorageService.instance.restoreFromBackupIfNeeded();
  // The permission-free restore path, and the reason storage is now optional.
  // `backup.json` is unreadable without the grant, so on a denied reinstall the
  // line above is a no-op and this is the ONLY thing between the user and
  // factory defaults. Safe to run unconditionally: it applies remote records
  // only to a freshly-installed DB, so it restores a wiped install but never
  // overwrites progression — or a deliberate reset — made on this phone.
  //
  // Bounded: this is N sequential network reads on the launch path, so a slow
  // or half-open connection would otherwise hold the UI on a blank screen.
  // Timing out is safe — it leaves `progression_synced_at` unset, so the next
  // launch retries and, until it succeeds, pushProgression refuses to
  // overwrite the remote copy.
  final restored = await ProgressionSyncService()
      .pullProgression()
      .timeout(
        const Duration(seconds: 20),
        onTimeout: () => const ProgressionSyncResult(
          changed: false,
          reason:
              'progression pull timed out after 20s — starting on local state; '
              'the next launch will retry',
        ),
      );
  debugPrint('WorkoutApp: ${restored.reason}');
  // Android-only transport: it exists so the PC can pull today's workout off
  // the phone over LAN. On the PC itself it would bind the very port the PC
  // scans, so it is skipped rather than serving the machine to itself.
  if (!Platform.isLinux) {
    await HttpServerService.instance.start();
  }
  runApp(const WorkoutApp());
}
// coverage:ignore-end

/// Root widget that bootstraps the app with Material 3 dark theming.
///
/// Also owns the app-lifecycle observer that stops [HttpServerService]'s
/// listening socket while the app is backgrounded, so the process (and its
/// open socket) doesn't sit alive indefinitely and block Doze/App-Standby.
class WorkoutApp extends StatefulWidget {
  /// Creates the root app widget.
  const WorkoutApp({super.key});

  @override
  State<WorkoutApp> createState() => _WorkoutAppState();
}

class _WorkoutAppState extends State<WorkoutApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // coverage:ignore-start
  // Platform edge, same shape as storage_service_schema's: the suite runs on
  // Linux, where this returns on the first line, so the switch below is
  // unreachable from any test this repo can run. Covering it would mean
  // threading a platform seam through the nine Platform.isLinux checks in
  // this app purely for test reachability.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The socket is never started on Linux (see main()), so there is nothing
    // to stop or restart here either.
    if (Platform.isLinux) return;
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        unawaited(HttpServerService.instance.stop());
      case AppLifecycleState.resumed:
        unawaited(HttpServerService.instance.start());
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
        break;
    }
  }
  // coverage:ignore-end

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Workout Tracker',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const HomeScreen(),
    );
  }
}
