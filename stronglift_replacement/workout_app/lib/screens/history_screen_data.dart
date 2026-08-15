// Pure transforms over the loaded history rows.
//
// Top-level rather than methods on the State: they only read `rows`, so
// keeping them off the widget makes the data shaping testable on its own.
// A `part` so they stay library-private -- see history_screen_charts.dart.
part of 'history_screen.dart';

Set<String> _exerciseDates(List<Map<String, dynamic>> rows, String name) {
  final result = <String>{};
  for (final row in rows) {
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

/// (date, total volume) per session – tonnage actually lifted, summed as
/// `weight × doneReps` over every logged set.
///
/// This deliberately uses the per-set actuals rather than
/// `targetWeight × targetSets × targetReps`: with targets, a session where
/// every set failed plotted identically to one completed in full, so the
/// line only moved when progression changed the target.
///
/// The target-based fallback is defensive only — `ExerciseResult.toJson`
/// has emitted `sets` since the app's first commit, so no row written by
/// this app lacks it. It exists for hand-edited or truncated backup JSON,
/// not for a migration that ever happened.
List<(DateTime, double)> _totalVolumePoints(List<Map<String, dynamic>> rows) {
  final points = <(DateTime, double)>[];
  for (final row in rows.reversed) {
    final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
    double total = 0;
    for (final ex in (json['exercises'] as List? ?? const [])) {
      final m = ex as Map<String, dynamic>;
      final sets = m['sets'] as List?;
      if (sets == null || sets.isEmpty) {
        final w = (m['targetWeight'] as num?)?.toDouble() ?? 0;
        final s = (m['targetSets'] as num?)?.toInt() ?? 0;
        final r = (m['targetReps'] as num?)?.toInt() ?? 0;
        total += w * s * r;
        continue;
      }
      for (final set in sets) {
        final sm = set as Map<String, dynamic>;
        // `weight` is a non-nullable double in SetResult and always
        // serialized, so there is no targetWeight fallback here — an absent
        // value would mean hand-edited JSON, and silently substituting the
        // target would overstate a set the user never did.
        final w = (sm['weight'] as num?)?.toDouble() ?? 0;
        total += w * ((sm['doneReps'] as num?)?.toInt() ?? 0);
      }
    }
    final date = DateTime.tryParse(row['date'] as String);
    if (date != null) points.add((date, total));
  }
  return points;
}

/// (date, weight) for the selected exercise.
List<(DateTime, double)> _exerciseWeightPoints(
  List<Map<String, dynamic>> rows,
  String name,
) {
  final points = <(DateTime, double)>[];
  for (final row in rows.reversed) {
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
List<Map<String, dynamic>> _sessionsForExercise(
  List<Map<String, dynamic>> rows,
  String name,
) {
  final result = <Map<String, dynamic>>[];
  for (final row in rows) {
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

/// Rolling average of 2 consecutive points to smooth A/B alternation.
List<(DateTime, double)> _rollingAvg2(List<(DateTime, double)> pts) {
  if (pts.length < 2) return pts;
  return [
    for (int i = 0; i < pts.length; i++)
      (pts[i].$1, i == 0 ? pts[0].$2 : (pts[i].$2 + pts[i - 1].$2) / 2),
  ];
}

/// All workout dates (YYYY-MM-DD): local sessions plus synced ones.
///
/// Synced dates are included so a day you only worked out on the PC (a
/// RunnerUp run) still marks the calendar here.
Set<String> _allWorkoutDates(
  List<Map<String, dynamic>> rows,
  List<Map<String, dynamic>> syncedRows,
) => {
  ...rows.map((r) => r['date'] as String),
  ...syncedRows.map((r) => '${r['date']}'),
};

/// Workouts the PC published that this phone has no local record of.
///
/// The PC pushes its whole `workout_log.json` (RunnerUp runs and manual
/// entries included), so pulling them here is what makes both devices show
/// the SAME history. Sorted newest-first to match the local session list.
/// StrongLifts sessions are deliberately excluded: they are restored into
/// local history instead, so listing them here too would double them up.
List<Map<String, dynamic>> _syncedOnly(List<Map<String, dynamic>> payloads) =>
    payloads.where((p) => _kSyncedOnlyKinds.contains(p['kind'])).toList()
      ..sort((a, b) => '${b['date']}'.compareTo('${a['date']}'));
