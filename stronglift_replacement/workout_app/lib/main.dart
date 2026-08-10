
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_device_id.dart';
import 'package:workout_app/ui/theme.dart';

// coverage:ignore-start
// App bootstrap: permission request, DB init, and a real listening socket —
// platform-channel work that can't run on the CI test host. The pieces it wires
// up are unit-tested individually; the entry point itself is not.
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Before anything that stamps an Hlc or syncs: until this resolves, the
  // device id falls back to the pre-migration constant.
  await initSyncDeviceId();
  // Storage permission MUST be settled before the DB is opened: opening it
  // seeds factory defaults for any missing exercise, and restoring afterwards
  // is a no-op once rows exist. Losing the race means a reinstall silently
  // comes up at defaults with months of progression gone -- which is what
  // happened on 2026-08-05.
  final storageGranted = await BackupService.instance
      .requestStoragePermission();
  if (!storageGranted) {
    debugPrint(
      'WorkoutApp: storage permission DENIED — the backup at $kBackupPath can '
      'neither be read nor written. Progression cannot be restored on this '
      'launch and will not be protected against the next reinstall.',
    );
  }
  await StorageService.init();
  await StorageService.instance.restoreFromBackupIfNeeded();
  await HttpServerService.instance.start();
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

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
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
