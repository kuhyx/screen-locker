/// Progress screen: total-load view plus per-exercise drill-down.
///
/// "Total" (default): total-volume chart, full calendar, all sessions.
/// Specific exercise: streak card, weight chart, exercise-only calendar,
/// exercise-only session list.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/done_today.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/calendar_widget.dart';

part 'history_screen_charts.dart';
part 'history_screen_data.dart';
part 'history_screen_painter.dart';
part 'history_screen_planned.dart';
part 'history_screen_tiles.dart';

const _kTotal = 'Total (all workouts)';

/// Screen showing workout history with per-exercise drill-down and charts.
class HistoryScreen extends StatefulWidget {
  /// Creates a [HistoryScreen].
  ///
  /// [httpClient] is injected only by tests, so the synced-workout fetch can
  /// be driven without real network — same pattern as `SettingsScreen`.
  ///
  /// [firebaseFactory] is likewise tests-only, and is NOT redundant with
  /// [httpClient]: the sync guard short-circuits on "no backend configured",
  /// and it asks Firebase that question directly. On a desktop that has a
  /// cached refresh token the real factory answers yes, so the guard opens and
  /// the fetch goes to the network even with the sync token faked away.
  const HistoryScreen({
    super.key,
    this.httpClient,
    this.firebaseFactory,
    this.clock,
  });

  /// Overrides the HTTP client used to read synced workouts (tests only).
  final http.Client? httpClient;

  /// Overrides how a Firebase account is discovered (tests only).
  final Future<FirebaseRestClient?> Function()? firebaseFactory;

  /// Decides which manual entries are still PLANNED (dated after today);
  /// defaults to [DateTime.now], injected by tests.
  final DateTime Function()? clock;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _rows = [];
  List<Map<String, dynamic>> _syncedRows = [];
  List<Map<String, dynamic>> _plannedRows = [];
  bool _loading = true;
  String _selected = _kTotal;
  List<String> _exerciseNames = [];
  ExerciseState? _selectedState;
  DateTime _calendarMonth = DateTime(DateTime.now().year, DateTime.now().month);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    // Put any of this device's own sessions that only exist remotely back into
    // the local table FIRST, so they show up in this same load. A reinstall
    // wipes local history while Firebase/GitHub keep it; without this the app
    // silently shows less history than actually happened.
    final remote = await _readSyncedPayloads();
    await StorageService.instance.restoreSyncedSessions(remote);
    final rows = await StorageService.instance.getWorkoutHistory(limit: 200);
    final names = <String>[];
    final seen = <String>{};
    for (final row in rows) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        final name = (ex as Map<String, dynamic>)['name'] as String;
        if (seen.add(name)) names.add(name);
      }
    }
    ExerciseState? state;
    if (_selected != _kTotal) {
      // Unreachable in practice: _load only runs from initState, where
      // _selected is still _kTotal; exercise selection goes through
      // _pickExercise, which loads its own state.
      // coverage:ignore-start
      state = await StorageService.instance.getExerciseState(_selected);
      // coverage:ignore-end
    }
    final today = dayKey((widget.clock ?? DateTime.now)());
    final synced = _syncedOnly(remote, today);
    final planned = _plannedOnly(remote, today);
    if (mounted) {
      setState(() {
        _rows = rows;
        _syncedRows = synced;
        _plannedRows = planned;
        _exerciseNames = names;
        _selectedState = state;
        _loading = false;
      });
    }
  }

  /// Every payload the sync backends hold, across all devices.
  ///
  /// Read once per load and used twice: to restore this device's own missing
  /// sessions into local history, and to list the PC-only records below them.
  Future<List<Map<String, dynamic>>> _readSyncedPayloads() =>
      _syncService().readMergedWorkoutPayloads();

  Future<void> _pickExercise(String name) async {
    ExerciseState? state;
    if (name != _kTotal) {
      state = await StorageService.instance.getExerciseState(name);
    }
    if (mounted) {
      setState(() {
        _selected = name;
        _selectedState = state;
      });
    }
  }

  // ── Data helpers ──────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final allNames = [_kTotal, ..._exerciseNames];
    final isTotal = _selected == _kTotal;

    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text('Progress', style: TextStyle(color: colorScheme.onSurface)),
        iconTheme: IconThemeData(color: colorScheme.onSurface),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          // Synced and planned entries count too: a phone with no local
          // sessions must still list (and let the user delete) its plans.
          : _rows.isEmpty && _syncedRows.isEmpty && _plannedRows.isEmpty
          ? Center(
              child: Text(
                'No workouts yet.',
                style: TextStyle(color: colorScheme.onSurfaceVariant),
              ),
            )
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _ExercisePicker(
                  names: allNames,
                  selected: _selected,
                  onChanged: _pickExercise,
                ),
                const SizedBox(height: 12),
                if (isTotal)
                  ..._buildTotalView()
                else
                  ..._buildExerciseView(_selected),
              ],
            ),
    );
  }

  List<Widget> _buildTotalView() => [
    ..._plannedSection(),
    const _SectionLabel('TOTAL VOLUME (2-session rolling avg, kg)'),
    const SizedBox(height: 6),
    _WeightChart(points: _rollingAvg2(_totalVolumePoints(_rows))),
    const SizedBox(height: 16),
    WorkoutCalendar(
      workoutDates: _allWorkoutDates(_rows, _syncedRows),
      month: _calendarMonth,
      onPrevMonth: () => setState(() {
        _calendarMonth = DateTime(
          _calendarMonth.year,
          _calendarMonth.month - 1,
        );
      }),
      onNextMonth: () => setState(() {
        _calendarMonth = DateTime(
          _calendarMonth.year,
          _calendarMonth.month + 1,
        );
      }),
    ),
    const SizedBox(height: 16),
    const _SectionLabel('ALL SESSIONS'),
    const SizedBox(height: 8),
    ..._rows.map((row) => _AllSessionTile(row: row)),
    if (_syncedRows.isNotEmpty) ...[
      const SizedBox(height: 16),
      const _SectionLabel('SYNCED FROM PC'),
      const SizedBox(height: 8),
      ..._syncedRows.map((row) => _SyncedWorkoutTile(payload: row)),
    ],
  ];

  List<Widget> _buildExerciseView(String name) => [
    if (_selectedState != null) ...[
      _ProgressStatsCard(state: _selectedState!),
      const SizedBox(height: 12),
    ],
    const _SectionLabel('WEIGHT OVER TIME'),
    const SizedBox(height: 6),
    _WeightChart(points: _exerciseWeightPoints(_rows, name)),
    const SizedBox(height: 16),
    WorkoutCalendar(
      workoutDates: _exerciseDates(_rows, name),
      month: _calendarMonth,
      onPrevMonth: () => setState(() {
        _calendarMonth = DateTime(
          _calendarMonth.year,
          _calendarMonth.month - 1,
        );
      }),
      onNextMonth: () => setState(() {
        _calendarMonth = DateTime(
          _calendarMonth.year,
          _calendarMonth.month + 1,
        );
      }),
    ),
    const SizedBox(height: 16),
    _SectionLabel(name.toUpperCase()),
    const SizedBox(height: 8),
    ..._sessionsForExercise(
      _rows,
      name,
    ).map((s) => _ExerciseSessionTile(session: s)),
  ];
}
