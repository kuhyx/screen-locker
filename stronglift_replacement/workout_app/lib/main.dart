import 'dart:async';

import 'package:flutter/material.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/storage_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await BackupService.instance.requestStoragePermission();
  await StorageService.init();
  await StorageService.instance.restoreFromBackupIfNeeded();
  await HttpServerService.instance.start();
  runApp(const WorkoutApp());
}

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
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.indigo,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
