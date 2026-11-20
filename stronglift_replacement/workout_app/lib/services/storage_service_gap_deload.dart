// The gap deload: cut a target after a training break, once, at load.
//
// Its own part next to storage_service_deload.dart: both write a target
// change plus its `progression_events` row in one transaction and share the
// `last_deloaded_at` stamp. See storage_service_backup.dart for why these are
// `part` extensions.
part of 'storage_service.dart';

/// Settings key stamped once the one-time backfill has run.
const String kGapDeloadBackfillKey = 'gap_deload_backfill_v1';

/// `progression_events.source` of a cut the app made by itself.
const String kAutoDeloadSource = 'auto';

/// One exercise's gap deload, as written.
class GapDeload {
  /// Creates a [GapDeload].
  const GapDeload({
    required this.name,
    required this.from,
    required this.to,
    required this.steps,
  });

  /// Exercise name.
  final String name;

  /// The target before the cut.
  final ProgressionTarget from;

  /// The target after it.
  final ProgressionTarget to;

  /// Regression steps the gap asked for (the 40% cap may have taken fewer).
  final int steps;
}

/// What [StorageServiceGapDeload.runGapDeloadBackfill] did.
class BackfillReport {
  /// Creates a report.
  const BackfillReport({
    required this.ran,
    required this.reason,
    this.deloads = const [],
  });

  /// Whether the backfill ran (and is now stamped).
  final bool ran;

  /// Why it did or did not, as a sentence.
  final String reason;

  /// Every exercise it cut.
  final List<GapDeload> deloads;
}

/// Gap deload at workout load, plus its one-time backfill.
extension StorageServiceGapDeload on StorageService {
  /// Every exercise's finished sessions, oldest first.
  ///
  /// Read from `workout_history`, which also holds sessions synced from other
  /// devices. Manual logs (table tennis, "other") name no exercise, so they
  /// cannot move a per-exercise gap.
  Future<Map<String, List<SessionMark>>> sessionMarks() async {
    final rows = await _db.query('workout_history', columns: ['date', 'json']);
    final marks = <String, List<SessionMark>>{};
    for (final row in rows) {
      final payload = StorageServiceSessions._decodeJson(row['json']);
      if (payload == null) continue;
      final ended = _sessionEnd(payload, row['date']);
      if (ended == null) {
        log(
          'StorageService: a session row has no readable end_time, '
          'start_time or date — it does not count toward any training gap.',
          level: 900,
        );
        continue;
      }
      final exercises = payload['exercises'];
      if (exercises is! List) continue;
      for (final ex in exercises) {
        if (ex is! Map || ex['name'] is! String) continue;
        marks
            .putIfAbsent(ex['name']! as String, () => [])
            .add(
              SessionMark(
                endedAt: ended,
                // -1: an old row with no target breaks every replay chain
                // instead of matching another unknown one.
                weight: (ex['targetWeight'] as num?)?.toDouble() ?? -1,
                reps: (ex['targetReps'] as num?)?.toInt() ?? -1,
              ),
            );
      }
    }
    for (final list in marks.values) {
      list.sort((a, b) => a.endedAt.compareTo(b.endedAt));
    }
    return marks;
  }

  /// Cuts every exercise whose last session is a week or more before [now].
  ///
  /// Skips an exercise deloaded (manually or by an earlier run of this)
  /// after its last session, so reopening the workout never cuts twice.
  /// With [includeOwed] (the backfill) the history's unpaid gaps are added
  /// on top -- see [missedGapSteps] -- and the lower of the two results wins.
  /// Every cut zeroes both streaks, stamps `last_deloaded_at` and logs a
  /// `progression_events` row of [kind], in one transaction.
  Future<List<GapDeload>> applyGapDeloads({
    DateTime? now,
    String kind = kGapDeloadKind,
    bool includeOwed = false,
  }) async {
    final at = now ?? DateTime.now();
    final marks = await sessionMarks();
    final done = <GapDeload>[];
    for (final state in await getAllExerciseStates()) {
      final history = marks[state.name];
      if (history == null || history.isEmpty) continue;
      final last = history.last.endedAt;
      final stamp = state.lastDeloadedAt;
      if (stamp != null && stamp.isAfter(last)) continue;
      final steps = gapDeloadSteps(gapCalendarDays(last, at));
      if (steps == 0) continue;

      var t = gapDeloadTarget(state, steps);
      var total = steps;
      if (includeOwed) {
        final owed = missedGapSteps(history);
        final replay = gapDeloadTarget(state, steps + owed);
        if (_lower(replay, t)) {
          t = replay;
          total = steps + owed;
        }
      }
      if (t.weight == state.weight && t.reps == state.reps) {
        log(
          'StorageService: ${state.name} is due $steps gap step(s) but '
          'already sits where the 40% cap stops them; left as is.',
        );
        continue;
      }
      if (await _writeGapDeload(state, t, at, kind)) {
        done.add(
          GapDeload(
            name: state.name,
            from: ProgressionTarget(state.weight, state.reps),
            to: t,
            steps: total,
          ),
        );
        log(
          'StorageService: $kind ${state.name} after '
          '${gapCalendarDays(last, at)} days: '
          '${_deloadKg(state.weight)} kg × ${state.reps} → '
          '${_deloadKg(t.weight)} kg × ${t.reps}',
        );
      }
    }
    if (done.isNotEmpty) unawaited(_backupNow());
    return done;
  }

  /// The newest gap or backfill deload per exercise that no session has
  /// followed yet: what the tile shows struck through.
  Future<Map<String, ProgressionEvent>> activeGapDeloads() async {
    final marks = await sessionMarks();
    final shown = <String, ProgressionEvent>{};
    for (final e in await getProgressionEvents()) {
      if (e.kind != kGapDeloadKind && e.kind != kBackfillDeloadKind) continue;
      if (shown.containsKey(e.exercise)) continue; // newest first
      final history = marks[e.exercise];
      if (history != null &&
          history.isNotEmpty &&
          !history.last.endedAt.isBefore(e.at)) {
        continue;
      }
      shown[e.exercise] = e;
    }
    return shown;
  }

  /// The one-time repair of the data the broken rule left behind.
  ///
  /// [writeExport] receives a JSON export of `exercise_state` BEFORE any cut;
  /// if it throws, nothing is cut and the stamp stays unset, so the next
  /// launch retries. Then every exercise last trained a week or more ago is
  /// cut by its current gap plus whatever the history still owes. Exercises
  /// trained since are left alone. Runs once: [kGapDeloadBackfillKey].
  Future<BackfillReport> runGapDeloadBackfill({
    required Future<void> Function(String json) writeExport,
    DateTime? now,
  }) async {
    final stamp = await _getSetting(kGapDeloadBackfillKey);
    if (stamp != null) {
      return BackfillReport(
        ran: false,
        reason: 'gap deload backfill already ran at $stamp',
      );
    }
    final export = jsonEncode({
      'format': kExportFormat,
      'version': kExportVersion,
      'exported_at': DateTime.now().toIso8601String(),
      'exercise_state': await _db.query('exercise_state', orderBy: 'name'),
    });
    try {
      await writeExport(export);
    } on Object catch (error, stackTrace) {
      final reason =
          'gap deload backfill NOT run: the pre-cut export of exercise_state '
          'could not be saved ($error), so nothing was cut; the next launch '
          'retries';
      log(
        'StorageService: $reason',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return BackfillReport(ran: false, reason: reason);
    }
    final deloads = await applyGapDeloads(
      now: now,
      kind: kBackfillDeloadKind,
      includeOwed: true,
    );
    await _setSetting(
      kGapDeloadBackfillKey,
      (now ?? DateTime.now()).toIso8601String(),
    );
    final reason = 'gap deload backfill cut ${deloads.length} exercise(s)';
    log('StorageService: $reason');
    return BackfillReport(ran: true, reason: reason, deloads: deloads);
  }

  Future<bool> _writeGapDeload(
    ExerciseState state,
    ProgressionTarget t,
    DateTime at,
    String kind,
  ) => _db.transaction((txn) async {
    final rows = await txn.update(
      'exercise_state',
      {
        'weight': t.weight,
        'reps': t.reps,
        'success_streak': 0,
        'fail_streak': 0,
        'last_deloaded_at': at.toIso8601String(),
        'updated_at': _nowMs(),
      },
      where: 'name = ?',
      whereArgs: [state.name],
    );
    if (rows != 1) {
      log(
        'StorageService: ${state.name} vanished from exercise_state during '
        'its gap deload; nothing was cut or logged.',
        level: 900,
      );
      return false;
    }
    await txn.insert('progression_events', {
      'at': at.toIso8601String(),
      'exercise': state.name,
      'kind': kind,
      'source': kAutoDeloadSource,
      'from_weight': state.weight,
      'from_reps': state.reps,
      'to_weight': t.weight,
      'to_reps': t.reps,
    });
    return true;
  });
}

/// Whether [a] is a lighter target than [b]: weight first, then reps.
bool _lower(ProgressionTarget a, ProgressionTarget b) =>
    a.weight < b.weight || (a.weight == b.weight && a.reps < b.reps);

/// When a session payload ended: `end_time`, else `start_time`, else the
/// row's `date`.
DateTime? _sessionEnd(Map<String, dynamic> payload, Object? rowDate) {
  for (final raw in [payload['end_time'], payload['start_time'], rowDate]) {
    if (raw is String) {
      final parsed = DateTime.tryParse(raw);
      if (parsed != null) return parsed;
    }
  }
  return null;
}

/// Reads a stored `last_deloaded_at`; anything unreadable is reported and
/// treated as "never", which lets the gap rule decide.
DateTime? _parseDeloadStamp(Object? raw) {
  if (raw == null) return null;
  final parsed = raw is String ? DateTime.tryParse(raw) : null;
  if (parsed == null) {
    log(
      'StorageService: unreadable last_deloaded_at "$raw" — treating the '
      'exercise as never deloaded.',
      level: 900,
    );
  }
  return parsed;
}
