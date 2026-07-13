/// Home screen: auto-resumes an active session, shows done-today status.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/storage_service.dart';

/// Home screen: auto-resumes active sessions and shows done-today status.
class HomeScreen extends StatefulWidget {
  /// Creates a [HomeScreen].
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late List<Exercise> _exercises;
  String _nextType = 'A';
  List<String> _serverAddresses = [];
  bool _loading = true;
  bool _doneToday = false;
  Map<String, dynamic>? _savedSession;

  /// True after the first load auto-navigated to an in-progress workout,
  /// so returning from workout does not auto-navigate again.
  bool _hasAutoResumed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final storage = StorageService.instance;
    final nextType = await storage.getNextWorkoutType();
    final exercises = await storage.getCurrentExercises(nextType);
    final saved = await storage.loadActiveSession();
    final addrs = await HttpServerService.instance.localAddresses;
    final lastDate = await storage.getLastWorkoutDate();
    final today = DateTime.now();
    final doneToday =
        lastDate != null &&
        lastDate.year == today.year &&
        lastDate.month == today.month &&
        lastDate.day == today.day;

    if (mounted) {
      setState(() {
        _nextType = nextType;
        _exercises = exercises;
        _serverAddresses = addrs;
        _savedSession = saved;
        _doneToday = doneToday;
        _loading = false;
      });

      // Auto-resume active session on first load (app launch).
      if (saved != null && !_hasAutoResumed) {
        _hasAutoResumed = true;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) unawaited(_openWorkout(resume: true));
        });
      }
    }
  }

  Future<void> _openWorkout({bool resume = false}) async {
    final storage = StorageService.instance;
    Map<String, dynamic>? savedState;
    var type = _nextType;
    var exercises = _exercises;

    if (resume && _savedSession != null) {
      savedState = _savedSession;
      final savedType = savedState!['workoutType'] as String? ?? _nextType;
      type = savedType;
      exercises = await storage.getCurrentExercises(savedType);
    }

    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => WorkoutScreen(
          workoutType: type,
          exercises: exercises,
          savedState: savedState,
        ),
      ),
    );
    unawaited(_load());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey.shade900,
      appBar: AppBar(
        backgroundColor: Colors.grey.shade800,
        title: const Text(
          'Workout Tracker',
          style: TextStyle(color: Colors.white),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.edit_note, color: Colors.white),
            tooltip: 'Log manual workout',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const ManualWorkoutScreen(),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.history, color: Colors.white),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings, color: Colors.white),
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const SettingsScreen(),
                ),
              );
              unawaited(_load());
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _WorkoutCard(
                    type: _nextType,
                    exercises: _exercises,
                    doneToday: _doneToday,
                    hasActiveSession: _savedSession != null,
                    onStart: _openWorkout,
                    onResume: () => _openWorkout(resume: true),
                  ),
                  const SizedBox(height: 20),
                  ServerAddressTile(addresses: _serverAddresses),
                ],
              ),
            ),
    );
  }
}

// ── Sub-widgets ──────────────────────────────────────────────────────────────

class _WorkoutCard extends StatelessWidget {
  const _WorkoutCard({
    required this.type,
    required this.exercises,
    required this.doneToday,
    required this.hasActiveSession,
    required this.onStart,
    required this.onResume,
  });

  final String type;
  final List<Exercise> exercises;
  final bool doneToday;
  final bool hasActiveSession;
  final VoidCallback onStart;
  final VoidCallback onResume;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.grey.shade800,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (doneToday && !hasActiveSession) ...[
              const Row(
                children: [
                  Icon(Icons.check_circle, color: Colors.greenAccent, size: 18),
                  SizedBox(width: 8),
                  Text(
                    'Done for today!',
                    style: TextStyle(
                      color: Colors.greenAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 15,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'Next: Workout $type — tomorrow',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ] else ...[
              Text(
                hasActiveSession
                    ? 'Workout $type in progress'
                    : 'Next: Workout $type',
                style: TextStyle(
                  color: hasActiveSession ? Colors.orangeAccent : Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
            const SizedBox(height: 10),
            ...exercises.map(
              (e) => Text(
                '${e.name}  ${e.sets}×${e.reps}×${e.weight}kg',
                style: const TextStyle(color: Colors.white70, fontSize: 13),
              ),
            ),
            const SizedBox(height: 14),
            if (hasActiveSession)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.orange.shade800,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: onResume,
                  child: const Text(
                    'Resume Workout',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              )
            else if (!doneToday)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.indigo,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: onStart,
                  child: Text(
                    'Start Workout $type',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Displays the LAN addresses the workout HTTP server is reachable at, or a
/// "Server not started" placeholder when none are available. Public so the
/// empty-address fallback can be exercised in a widget test.
class ServerAddressTile extends StatelessWidget {
  /// Creates a tile listing [addresses] (may be empty).
  const ServerAddressTile({required this.addresses, super.key});

  final List<String> addresses;

  @override
  Widget build(BuildContext context) {
    final lines = addresses.isEmpty
        ? ['Server not started']
        : addresses.map((ip) => '$ip:$kWorkoutServerPort').toList();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'HTTP sync (no ADB needed)',
            style: TextStyle(
              color: Colors.white54,
              fontSize: 11,
              letterSpacing: 1.1,
            ),
          ),
          const SizedBox(height: 4),
          ...lines.map(
            (line) => Text(
              line,
              style: const TextStyle(
                color: Colors.white70,
                fontFamily: 'monospace',
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
