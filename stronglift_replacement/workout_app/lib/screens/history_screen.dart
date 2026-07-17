/// Progress screen: total-load view plus per-exercise drill-down.
///
/// "Total" (default): total-volume chart, full calendar, all sessions.
/// Specific exercise: streak card, weight chart, exercise-only calendar,
/// exercise-only session list.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/widgets/calendar_widget.dart';

const _kTotal = 'Total (all workouts)';

/// Screen showing workout history with per-exercise drill-down and charts.
class HistoryScreen extends StatefulWidget {
  /// Creates a [HistoryScreen].
  ///
  /// [httpClient] is injected only by tests, so the synced-workout fetch can
  /// be driven without real network — same pattern as `SettingsScreen`.
  const HistoryScreen({super.key, this.httpClient});

  /// Overrides the HTTP client used to read synced workouts (tests only).
  final http.Client? httpClient;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

/// Synced kinds this phone has no local record of, so showing them can't
/// double up an existing session.
///
/// A `phone_verified` record is the PC's mirror of a StrongLifts session this
/// phone already stores in full (and renders from `_rows`), so it is
/// deliberately excluded — otherwise the same workout would appear twice.
const _kSyncedOnlyKinds = {'runnerup_verified', 'manual_workout'};

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _rows = [];
  List<Map<String, dynamic>> _syncedRows = [];
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
    final synced = await _loadSyncedWorkouts();
    if (mounted) {
      setState(() {
        _rows = rows;
        _syncedRows = synced;
        _exerciseNames = names;
        _selectedState = state;
        _loading = false;
      });
    }
  }

  /// Workouts the PC published that this phone has no local record of.
  ///
  /// The PC pushes its whole `workout_log.json` (RunnerUp runs and manual
  /// entries included), so pulling them here is what makes both devices show
  /// the SAME history. Sorted newest-first to match the local session list.
  Future<List<Map<String, dynamic>>> _loadSyncedWorkouts() async {
    final payloads = await WorkoutSyncService(
      httpClient: widget.httpClient,
    ).readMergedWorkoutPayloads();
    final synced = payloads
        .where((p) => _kSyncedOnlyKinds.contains(p['kind']))
        .toList()
      ..sort((a, b) => '${b['date']}'.compareTo('${a['date']}'));
    return synced;
  }

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

  /// All workout dates (YYYY-MM-DD): local sessions plus synced ones.
  ///
  /// Synced dates are included so a day you only worked out on the PC (a
  /// RunnerUp run) still marks the calendar here.
  Set<String> get _allWorkoutDates => {
    ..._rows.map((r) => r['date'] as String),
    ..._syncedRows.map((r) => '${r['date']}'),
  };

  /// Dates when the selected exercise appeared.
  Set<String> _exerciseDates(String name) {
    final result = <String>{};
    for (final row in _rows) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        if ((ex as Map<String, dynamic>)['name'] == name) {
          result.add(row['date'] as String);
          break;
        }
      }
    }
    return result;
  }

  /// (date, total volume) per session – sum of targetWeight × targetSets.
  List<(DateTime, double)> _totalVolumePoints() {
    final points = <(DateTime, double)>[];
    for (final row in _rows.reversed) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      double total = 0;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        final m = ex as Map<String, dynamic>;
        final w = (m['targetWeight'] as num?)?.toDouble() ?? 0;
        final s = (m['targetSets'] as num?)?.toInt() ?? 0;
        final r = (m['targetReps'] as num?)?.toInt() ?? 0;
        total += w * s * r;
      }
      final date = DateTime.tryParse(row['date'] as String);
      if (date != null) points.add((date, total));
    }
    return points;
  }

  /// (date, weight) for the selected exercise.
  List<(DateTime, double)> _exerciseWeightPoints(String name) {
    final points = <(DateTime, double)>[];
    for (final row in _rows.reversed) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        final m = ex as Map<String, dynamic>;
        if (m['name'] == name) {
          final date = DateTime.tryParse(row['date'] as String);
          final w = (m['targetWeight'] as num?)?.toDouble();
          if (date != null && w != null) points.add((date, w));
          break;
        }
      }
    }
    return points;
  }

  /// Sessions filtered to those containing the selected exercise, newest first.
  List<Map<String, dynamic>> _sessionsForExercise(String name) {
    final result = <Map<String, dynamic>>[];
    for (final row in _rows) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        final m = ex as Map<String, dynamic>;
        if (m['name'] == name) {
          result.add({...row, 'exerciseData': m});
          break;
        }
      }
    }
    return result;
  }

  // ── Build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final allNames = [_kTotal, ..._exerciseNames];
    final isTotal = _selected == _kTotal;

    return Scaffold(
      backgroundColor: Colors.grey.shade900,
      appBar: AppBar(
        backgroundColor: Colors.grey.shade800,
        title: const Text('Progress', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _rows.isEmpty
          ? const Center(
              child: Text(
                'No workouts yet.',
                style: TextStyle(color: Colors.white54),
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

  /// Rolling average of 2 consecutive points to smooth A/B alternation.
  static List<(DateTime, double)> _rollingAvg2(
    List<(DateTime, double)> pts,
  ) {
    if (pts.length < 2) return pts;
    return [
      for (int i = 0; i < pts.length; i++)
        (pts[i].$1, i == 0 ? pts[0].$2 : (pts[i].$2 + pts[i - 1].$2) / 2),
    ];
  }

  List<Widget> _buildTotalView() => [
    const _SectionLabel('TOTAL VOLUME (2-session rolling avg, kg)'),
    const SizedBox(height: 6),
    _WeightChart(
      points: _rollingAvg2(_totalVolumePoints()),
    ),
    const SizedBox(height: 16),
    WorkoutCalendar(
      workoutDates: _allWorkoutDates,
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
    _WeightChart(
      points: _exerciseWeightPoints(name),
    ),
    const SizedBox(height: 16),
    WorkoutCalendar(
      workoutDates: _exerciseDates(name),
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
    ..._sessionsForExercise(name).map((s) => _ExerciseSessionTile(session: s)),
  ];
}

// ── Shared sub-widgets ──────────────────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.white54,
        fontSize: 11,
        letterSpacing: 1.3,
      ),
    );
  }
}

class _ExercisePicker extends StatelessWidget {
  const _ExercisePicker({
    required this.names,
    required this.selected,
    required this.onChanged,
  });

  final List<String> names;
  final String selected;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButton<String>(
      value: selected,
      dropdownColor: Colors.grey.shade800,
      style: const TextStyle(color: Colors.white),
      underline: const SizedBox(),
      isExpanded: true,
      items: names
          .map(
            (n) => DropdownMenuItem(
              value: n,
              child: Text(
                n,
                style: TextStyle(
                  color: n == _kTotal ? Colors.white70 : Colors.white,
                  fontStyle: n == _kTotal ? FontStyle.italic : FontStyle.normal,
                ),
              ),
            ),
          )
          .toList(),
      onChanged: (v) {
        if (v != null) onChanged(v);
      },
    );
  }
}

class _ProgressStatsCard extends StatelessWidget {
  const _ProgressStatsCard({required this.state});

  final ExerciseState state;

  String _nextWeightLabel(double current, double max, double inc) {
    if (current >= max) return '+1 rep';
    return '+${inc}kg (${(current + inc).clamp(0.0, max)}kg)';
  }

  String _prevWeightLabel(double current, double inc) {
    return '-${inc}kg (${(current - inc).clamp(0.0, double.infinity)}kg)';
  }

  @override
  Widget build(BuildContext context) {
    final successLeft = state.successThreshold - state.successStreak;
    final failLeft = state.failThreshold - state.failStreak;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${state.name}  —  ${state.weight}kg',
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 8),
          _StreakRow(
            icon: Icons.trending_up,
            color: Colors.greenAccent,
            current: state.successStreak,
            threshold: state.successThreshold,
            leftLabel: '$successLeft more',
            actionLabel: _nextWeightLabel(
              state.weight,
              state.maxWeight,
              kWeightIncrement,
            ),
            direction: '↑',
          ),
          const SizedBox(height: 6),
          _StreakRow(
            icon: Icons.trending_down,
            color: Colors.redAccent,
            current: state.failStreak,
            threshold: state.failThreshold,
            leftLabel: '$failLeft more',
            actionLabel: _prevWeightLabel(state.weight, kWeightIncrement),
            direction: '↓',
          ),
        ],
      ),
    );
  }
}

class _StreakRow extends StatelessWidget {
  const _StreakRow({
    required this.icon,
    required this.color,
    required this.current,
    required this.threshold,
    required this.leftLabel,
    required this.actionLabel,
    required this.direction,
  });

  final IconData icon;
  final Color color;
  final int current;
  final int threshold;
  final String leftLabel;
  final String actionLabel;
  final String direction;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: color, size: 14),
        const SizedBox(width: 6),
        ...List.generate(
          threshold,
          (i) => Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(right: 3),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: i < current ? color : Colors.white24,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '$leftLabel to $direction $actionLabel',
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ),
      ],
    );
  }
}

class _WeightChart extends StatelessWidget {
  const _WeightChart({required this.points});

  final List<(DateTime, double)> points;

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) {
      return Container(
        height: 80,
        alignment: Alignment.center,
        child: const Text(
          'Not enough data for chart',
          style: TextStyle(color: Colors.white38),
        ),
      );
    }
    return SizedBox(
      height: 140,
      child: CustomPaint(
        painter: _ChartPainter(points),
        size: Size.infinite,
      ),
    );
  }
}

class _ChartPainter extends CustomPainter {
  _ChartPainter(this.points);

  final List<(DateTime, double)> points;

  // Layout constants
  static const _topPad = 14.0; // room for top Y label
  static const _bottomPad = 22.0; // room for X-axis dates
  static const _hPad = 8.0;

  static const _months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  static String _shortDate(DateTime d) => '${_months[d.month - 1]} ${d.day}';

  @override
  void paint(Canvas canvas, Size size) {
    final minW = points.map((p) => p.$2).reduce(min);
    final maxW = points.map((p) => p.$2).reduce(max);
    final minMs = points.first.$1.millisecondsSinceEpoch.toDouble();
    final maxMs = points.last.$1.millisecondsSinceEpoch.toDouble();
    final wRange = maxW - minW;
    final tRange = maxMs - minMs;

    const plotTop = _topPad;
    final plotBottom = size.height - _bottomPad;
    const plotLeft = _hPad;
    final plotRight = size.width - _hPad;
    final plotHeight = plotBottom - plotTop;
    final plotWidth = plotRight - plotLeft;

    double xOf(DateTime t) => tRange == 0
        ? (plotLeft + plotRight) / 2
        : (t.millisecondsSinceEpoch - minMs) / tRange * plotWidth + plotLeft;
    double yOf(double w) => wRange == 0
        ? (plotTop + plotBottom) / 2
        : (1 - (w - minW) / wRange) * plotHeight + plotTop;

    final linePaint = Paint()
      ..color = Colors.indigoAccent
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    final dotPaint = Paint()
      ..color = Colors.indigoAccent
      ..style = PaintingStyle.fill;

    final path = Path()..moveTo(xOf(points.first.$1), yOf(points.first.$2));
    for (final p in points.skip(1)) {
      path.lineTo(xOf(p.$1), yOf(p.$2));
    }
    canvas.drawPath(path, linePaint);
    for (final p in points) {
      canvas.drawCircle(Offset(xOf(p.$1), yOf(p.$2)), 4, dotPaint);
    }

    // Y-axis labels
    final tp = TextPainter(textDirection: TextDirection.ltr);
    void drawText(String text, Offset offset, {double fontSize = 10}) {
      tp
        ..text = TextSpan(
          text: text,
          style: TextStyle(color: Colors.white54, fontSize: fontSize),
        )
        ..layout()
        ..paint(canvas, offset);
    }

    drawText('${maxW.round()}kg', const Offset(plotLeft, 0));
    drawText('${minW.round()}kg', Offset(plotLeft, plotBottom + 2));

    // X-axis date labels: first, middle, last
    final n = points.length;
    final xIndices = n <= 2 ? [0, n - 1] : [0, n ~/ 2, n - 1];
    for (final i in xIndices) {
      final p = points[i];
      final label = _shortDate(p.$1);
      tp
        ..text = TextSpan(
          text: label,
          style: const TextStyle(color: Colors.white38, fontSize: 9),
        )
        ..layout();
      final cx = xOf(p.$1);
      final dx = (cx - tp.width / 2).clamp(plotLeft, plotRight - tp.width);
      tp.paint(canvas, Offset(dx, size.height - tp.height));
    }
  }

  @override
  bool shouldRepaint(_ChartPainter old) => old.points != points;
}

/// One workout the PC published that this phone has no local session for.
class _SyncedWorkoutTile extends StatelessWidget {
  const _SyncedWorkoutTile({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    final kind = '${payload['kind']}';
    final isRun = kind == 'runnerup_verified';
    final label = isRun ? 'Run' : 'Manual';
    final detail = '${payload['source'] ?? ''}';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isRun ? Colors.blue.shade800 : Colors.orange.shade900,
        ),
      ),
      child: Row(
        children: [
          Icon(
            isRun ? Icons.directions_run : Icons.edit_note,
            color: isRun ? Colors.blue.shade300 : Colors.orange.shade300,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${payload['date']}  ·  $label',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                if (detail.isNotEmpty)
                  Text(
                    detail,
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AllSessionTile extends StatelessWidget {
  const _AllSessionTile({required this.row});

  final Map<String, dynamic> row;

  String _formatDuration(int secs) {
    final h = secs ~/ 3600;
    final m = (secs ~/ 60).remainder(60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return h > 0 ? '${h}h ${m}m ${s}s' : '${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final succeeded = (row['succeeded'] as int) == 1;
    final type = row['workout_type'] as String;
    final date = row['date'] as String;
    final dur = _formatDuration(row['duration_seconds'] as int);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: succeeded ? Colors.green.shade800 : Colors.red.shade900,
        ),
      ),
      child: Row(
        children: [
          Icon(
            succeeded ? Icons.check_circle : Icons.cancel,
            color: succeeded ? Colors.greenAccent : Colors.redAccent,
            size: 18,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Workout $type  ·  $date',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  dur,
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ExerciseSessionTile extends StatelessWidget {
  const _ExerciseSessionTile({required this.session});

  final Map<String, dynamic> session;

  String _formatDuration(int secs) {
    final h = secs ~/ 3600;
    final m = (secs ~/ 60).remainder(60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return h > 0 ? '${h}h ${m}m ${s}s' : '${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final exData = session['exerciseData'] as Map<String, dynamic>;
    final succeeded = (exData['succeeded'] as bool?) == true;
    final date = session['date'] as String;
    final dur = _formatDuration(session['duration_seconds'] as int);
    final weight = (exData['targetWeight'] as num?)?.toDouble();
    final warmupDone = exData['warmupDone'] as bool? ?? false;
    final sets = (exData['sets'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final targetSets = exData['targetSets'] as int? ?? sets.length;
    final doneSets = sets.where((s) => s['succeeded'] == true).length;
    final repsSummary = sets.map((s) => '${s['doneReps']}').join(', ');

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: succeeded ? Colors.green.shade800 : Colors.red.shade900,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              succeeded ? Icons.check_circle : Icons.cancel,
              color: succeeded ? Colors.greenAccent : Colors.redAccent,
              size: 18,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  date,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${weight ?? '?'}kg  ·  $doneSets/$targetSets sets'
                  '  ·  ${warmupDone ? '⬤ warmup' : '○ no warmup'}',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                  ),
                ),
                if (repsSummary.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    'reps: $repsSummary',
                    style: const TextStyle(
                      color: Colors.white54,
                      fontSize: 11,
                    ),
                  ),
                ],
                const SizedBox(height: 2),
                Text(
                  'workout: $dur',
                  style: const TextStyle(
                    color: Colors.white38,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
