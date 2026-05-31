/// History screen: past workout list with per-exercise weight progress chart.
library;

import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:workout_app/services/storage_service.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;
  String? _selectedExercise;
  List<String> _exerciseNames = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final rows = await StorageService.instance.getWorkoutHistory();
    final names = <String>{};
    for (final row in rows) {
      final json =
          jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List)) {
        names.add((ex as Map<String, dynamic>)['name'] as String);
      }
    }
    if (mounted) {
      setState(() {
        _rows = rows;
        _exerciseNames = names.toList();
        _selectedExercise =
            _exerciseNames.isNotEmpty ? _exerciseNames.first : null;
        _loading = false;
      });
    }
  }

  String _formatDuration(int secs) {
    final m = (secs ~/ 60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return '${secs ~/ 3600 > 0 ? '${secs ~/ 3600}h ' : ''}${m}m ${s}s';
  }

  /// Extract (date, weight) points for the selected exercise from history.
  List<(DateTime, double)> _buildChartPoints(String exerciseName) {
    final points = <(DateTime, double)>[];
    for (final row in _rows.reversed) {
      final json =
          jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List)) {
        final m = ex as Map<String, dynamic>;
        if (m['name'] == exerciseName) {
          final date = DateTime.tryParse(row['date'] as String);
          final weight = (m['targetWeight'] as num?)?.toDouble();
          if (date != null && weight != null) {
            points.add((date, weight));
          }
        }
      }
    }
    return points;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey.shade900,
      appBar: AppBar(
        backgroundColor: Colors.grey.shade800,
        title: const Text('History', style: TextStyle(color: Colors.white)),
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
                    if (_selectedExercise != null) ...[
                      _ExercisePicker(
                        names: _exerciseNames,
                        selected: _selectedExercise!,
                        onChanged: (v) =>
                            setState(() => _selectedExercise = v),
                      ),
                      const SizedBox(height: 8),
                      _WeightChart(
                        points: _buildChartPoints(_selectedExercise!),
                      ),
                      const SizedBox(height: 16),
                    ],
                    const Text(
                      'SESSIONS',
                      style: TextStyle(
                        color: Colors.white54,
                        fontSize: 11,
                        letterSpacing: 1.3,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ..._rows.map((row) => _SessionTile(
                          row: row,
                          formatDuration: _formatDuration,
                        )),
                  ],
                ),
    );
  }
}

// ── Sub-widgets ────────────────────────────────────────────────────────────────

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
              child: Text(n, style: const TextStyle(color: Colors.white)),
            ),
          )
          .toList(),
      onChanged: (v) {
        if (v != null) onChanged(v);
      },
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
        height: 100,
        alignment: Alignment.center,
        child: const Text(
          'Not enough data',
          style: TextStyle(color: Colors.white38),
        ),
      );
    }
    return SizedBox(
      height: 120,
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

  @override
  void paint(Canvas canvas, Size size) {
    final minW = points.map((p) => p.$2).reduce(min);
    final maxW = points.map((p) => p.$2).reduce(max);
    final minMs = points.first.$1.millisecondsSinceEpoch.toDouble();
    final maxMs = points.last.$1.millisecondsSinceEpoch.toDouble();
    final wRange = maxW - minW;
    final tRange = maxMs - minMs;

    double xOf(DateTime t) =>
        tRange == 0 ? size.width / 2 :
        (t.millisecondsSinceEpoch - minMs) / tRange * (size.width - 16) + 8;
    double yOf(double w) =>
        wRange == 0 ? size.height / 2 :
        (1 - (w - minW) / wRange) * (size.height - 16) + 8;

    final linePaint = Paint()
      ..color = Colors.indigoAccent
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    final dotPaint = Paint()
      ..color = Colors.indigoAccent
      ..style = PaintingStyle.fill;

    final path = Path()
      ..moveTo(xOf(points.first.$1), yOf(points.first.$2));
    for (final p in points.skip(1)) {
      path.lineTo(xOf(p.$1), yOf(p.$2));
    }
    canvas.drawPath(path, linePaint);

    for (final p in points) {
      canvas.drawCircle(Offset(xOf(p.$1), yOf(p.$2)), 4, dotPaint);
    }

    // Label min/max weight
    final tp = TextPainter(textDirection: TextDirection.ltr);
    void drawLabel(String text, Offset offset) {
      tp
        ..text = TextSpan(
          text: text,
          style: const TextStyle(color: Colors.white54, fontSize: 10),
        )
        ..layout()
        ..paint(canvas, offset);
    }
    drawLabel('${maxW}kg', Offset(8, 0));
    drawLabel('${minW}kg', Offset(8, size.height - 14));
  }

  @override
  bool shouldRepaint(_ChartPainter old) => old.points != points;
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({
    required this.row,
    required this.formatDuration,
  });

  final Map<String, dynamic> row;
  final String Function(int) formatDuration;

  @override
  Widget build(BuildContext context) {
    final succeeded = (row['succeeded'] as int) == 1;
    final type = row['workout_type'] as String;
    final date = row['date'] as String;
    final dur = formatDuration(row['duration_seconds'] as int);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: succeeded ? Colors.green.shade800 : Colors.red.shade900,
          width: 1,
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
