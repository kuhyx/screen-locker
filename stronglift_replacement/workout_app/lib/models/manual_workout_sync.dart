// The sync payload and record id for a manual workout.
//
// The key strings here are a cross-language contract with the Python
// side's build_sync_payload / manual_sync_record_id -- a shared literal
// fixture test pins them on both sides. Moving the code must not touch
// a single key.
part of 'manual_workout.dart';

/// Builds the cross-device sync payload: [buildEntry] + `kind` + `date`.
Map<String, Object?> buildSyncPayload(ManualWorkoutDraft draft, String date) {
  return <String, Object?>{
    ...buildEntry(draft),
    'kind': kManualWorkoutSyncKind,
    'date': date,
  };
}

/// The stable crdt-sync record id for a manual workout.
///
/// Format: `manual:<date>T<HH:MM>`.
String manualSyncRecordId(String date, String startTime) =>
    'manual:${date}T${startTime.trim()}';

/// Builds the crdt-sync [Record] for a manual workout, stamped with [hlc].
///
/// [date] is the WORKOUT date, which may be up to a week ahead of the day it
/// is logged on: the PC credits a planned entry on its own date, never early.
Record buildManualRecord(
  ManualWorkoutDraft draft,
  String date, {
  required Hlc hlc,
}) {
  return Record(
    id: manualSyncRecordId(date, draft.startTime),
    fields: {'payload': (buildSyncPayload(draft, date), hlc)},
  );
}

/// The tombstone that deletes the manual workout [recordId] on every device.
///
/// Carries no fields: [mergeRecord] keeps whatever payload this device's log
/// already holds and only flips `deleted`, which is sticky. A record logged
/// on another device gets a field-less tombstone here, and both readers
/// (this app's and the PC's `_tombstoned_ids`) suppress across the whole
/// device union, so that is enough. Deleting `log.json` locally instead would
/// just be re-ingested on the next sync.
Record buildManualTombstone(String recordId, {required Hlc hlc}) =>
    Record(id: recordId, fields: const {}, deleted: true, deletedHlc: hlc);

/// Manual-workout counts in the rolling 7-/30-day windows (the shared budget).
class ManualBudget {
  /// Creates a budget snapshot.
  const ManualBudget({required this.week, required this.month});

  /// Manual workouts in the fullest 7-day window containing the workout
  /// date (see [countManualBudget]).
  final int week;

  /// Manual workouts in the fullest 30-day window containing the workout
  /// date.
  final int month;

  /// Whether either window has reached its limit.
  bool get exhausted =>
      week >= kManualWorkoutBudgetPer7Days ||
      month >= kManualWorkoutBudgetPer30Days;
}
