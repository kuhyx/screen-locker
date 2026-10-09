// Manual deload and the progression_events audit trail it writes.
//
// Its own part because it owns its own table: exercises.dart edits a row in
// place, this one changes the target AND records why, atomically. See
// storage_service_backup.dart for why these are `part` extensions.
part of 'storage_service.dart';

/// Manual deload and the `progression_events` log.
extension StorageServiceDeload on StorageService {
  /// Steps [name]'s target down once, exactly as a fail streak would.
  ///
  /// The step is [targetAfterFailure], so a manual deload lands where the
  /// automatic one would have, in whatever mode the exercise is in. Streaks
  /// are cleared like every other hand edit: the old ones counted workouts at
  /// a target that no longer exists.
  ///
  /// The target change and its `progression_events` row are written in one
  /// transaction, so the log can never claim a deload that did not happen or
  /// miss one that did. Returns a null [ManualDeloadResult.state] -- with the
  /// reason -- when nothing changed.
  Future<ManualDeloadResult> manualDeload(
    String name, {
    required DeloadSource source,
  }) async {
    final state = await getExerciseState(name);
    if (state == null) {
      return _deloadRefused(
        'No saved state for "$name", so there is nothing to deload. '
        'Reopen the app to re-seed the exercise defaults.',
      );
    }

    final t = targetAfterFailure(state);
    final from = '${_deloadKg(state.weight)} kg × ${state.reps}';
    if (t.weight == state.weight && t.reps == state.reps) {
      // weight mode at 0 kg, reps mode at 1 rep, double progression at the
      // low rep count with no weight left: the rule has nowhere lower to go.
      return _deloadRefused(
        '$name is already at $from, the lowest target its '
        '${state.mode.storageKey} progression can step down to. '
        'Nothing was changed.',
      );
    }

    final changed = await _db.transaction((txn) async {
      final rows = await txn.update(
        'exercise_state',
        {
          'weight': t.weight,
          'reps': t.reps,
          'success_streak': 0,
          'fail_streak': 0,
        },
        where: 'name = ?',
        whereArgs: [name],
      );
      // Only log what actually landed: a row deleted since the read above
      // must not leave an event describing a deload nobody received.
      if (rows != 1) return false;
      await txn.insert('progression_events', {
        'at': DateTime.now().toIso8601String(),
        'exercise': name,
        'kind': kManualDeloadKind,
        'source': source.storageKey,
        'from_weight': state.weight,
        'from_reps': state.reps,
        'to_weight': t.weight,
        'to_reps': t.reps,
      });
      return true;
    });
    if (!changed) {
      return _deloadRefused(
        '$name disappeared from exercise_state while deloading; '
        'nothing was changed or logged.',
      );
    }

    unawaited(_backupNow());
    final reason = '$name: $from → ${_deloadKg(t.weight)} kg × ${t.reps}';
    log('StorageService: manual deload (${source.storageKey}) $reason');
    return ManualDeloadResult(
      state: state.copyWith(
        weight: t.weight,
        reps: t.reps,
        successStreak: 0,
        failStreak: 0,
      ),
      reason: reason,
    );
  }

  /// Every logged target change, newest first; only [exercise]'s if given.
  ///
  /// A row whose `at` does not parse is skipped with a warning rather than
  /// failing the whole list: one corrupt row should not hide the others.
  Future<List<ProgressionEvent>> getProgressionEvents({
    String? exercise,
  }) async {
    final rows = await _db.query(
      'progression_events',
      where: exercise == null ? null : 'exercise = ?',
      whereArgs: exercise == null ? null : [exercise],
      // `id` breaks ties between events logged within the same microsecond.
      orderBy: 'at DESC, id DESC',
    );
    final events = <ProgressionEvent>[];
    for (final r in rows) {
      final at = DateTime.tryParse(r['at']! as String);
      if (at == null) {
        log(
          'StorageService: progression_events row ${r['id']} has an '
          'unparseable timestamp "${r['at']}" — leaving it out of the list. '
          'Some writer stored a non-ISO-8601 value.',
          level: 900,
        );
        continue;
      }
      events.add(
        ProgressionEvent(
          at: at,
          exercise: r['exercise']! as String,
          kind: r['kind']! as String,
          source: r['source']! as String,
          fromWeight: (r['from_weight']! as num).toDouble(),
          fromReps: r['from_reps']! as int,
          toWeight: (r['to_weight']! as num).toDouble(),
          toReps: r['to_reps']! as int,
        ),
      );
    }
    return events;
  }

  /// Logs [reason] as a warning and wraps it in a not-applied result.
  ManualDeloadResult _deloadRefused(String reason) {
    log('StorageService: manual deload refused — $reason', level: 900);
    return ManualDeloadResult(state: null, reason: reason);
  }
}

/// `100` for 100.0, `97.5` for 97.5 -- the same rendering as the progression
/// previews (`describeTargetChange`), whose helper is private to its library.
String _deloadKg(double w) =>
    w == w.roundToDouble() ? w.toInt().toString() : w.toString();
