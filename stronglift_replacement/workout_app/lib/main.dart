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
class WorkoutApp extends StatelessWidget {
  /// Creates the root app widget.
  const WorkoutApp({super.key});

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
