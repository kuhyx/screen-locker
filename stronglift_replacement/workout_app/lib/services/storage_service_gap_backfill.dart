// The one-time gap deload backfill: export, then cut what the broken rule
// left at the pre-gap max. Split from storage_service_gap_deload.dart, whose
// `applyGapDeloads` it runs with the backfill kind and the owed steps.
part of 'storage_service.dart';

/// Settings key stamped once the one-time backfill has run.
const String kGapDeloadBackfillKey = 'gap_deload_backfill_v1';

/// The one-time repair of existing data.
extension StorageServiceGapBackfill on StorageService {
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
}
