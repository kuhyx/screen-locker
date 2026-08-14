/// Home screen: auto-resumes an active session, shows done-today status.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

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
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Workout Tracker',
          style: TextStyle(color: colorScheme.onSurface),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.edit_note, color: colorScheme.onSurface),
            tooltip: 'Log manual workout',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const ManualWorkoutScreen(),
              ),
            ),
          ),
          IconButton(
            icon: Icon(Icons.history, color: colorScheme.onSurface),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const HistoryScreen()),
            ),
          ),
          IconButton(
            icon: Icon(Icons.settings, color: colorScheme.onSurface),
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
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    // Canonical button padding (rule 22): vertical 12, horizontal 24 — an
    // exact 2x ratio, both on the 4px spacing scale (tokens.md's own example).
    const buttonPadding = EdgeInsets.symmetric(horizontal: 24, vertical: 12);
    return Card(
      color: colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (doneToday && !hasActiveSession) ...[
              Row(
                children: [
                  Icon(Icons.check_circle, color: status.success, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Done for today!',
                    style: TextStyle(
                      color: status.success,
                      fontWeight: FontWeight.bold,
                      fontSize: AppTextSize.body,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'Next: Workout $type — tomorrow',
                style: TextStyle(
                  color: colorScheme.onSurface,
                  fontSize: AppTextSize.body,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ] else ...[
              Text(
                hasActiveSession
                    ? 'Workout $type in progress'
                    : 'Next: Workout $type',
                style: TextStyle(
                  color: hasActiveSession
                      ? status.warning
                      : colorScheme.onSurface,
                  fontSize: AppTextSize.subtitle,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
            const SizedBox(height: 10),
            ...exercises.map(
              (e) => Text(
                '${e.name}  ${e.sets}×${e.reps}×${e.weight}kg',
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  fontSize: AppTextSize.label,
                ),
              ),
            ),
            const SizedBox(height: 14),
            if (hasActiveSession)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: status.warning,
                    padding: buttonPadding,
                  ),
                  onPressed: onResume,
                  child: Text(
                    'Resume Workout',
                    style: TextStyle(
                      color: colorScheme.onPrimary,
                      fontSize: AppTextSize.body,
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
                    backgroundColor: colorScheme.primary,
                    padding: buttonPadding,
                  ),
                  onPressed: onStart,
                  child: Text(
                    'Start Workout $type',
                    style: TextStyle(
                      color: colorScheme.onPrimary,
                      fontSize: AppTextSize.body,
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
