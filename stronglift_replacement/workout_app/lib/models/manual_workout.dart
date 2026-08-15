/// Manual (off-app) workout model, validation, and sync-record building.
///
/// Mirrors the Python `screen_locker._manual_workout` module
/// (`ManualWorkoutDraft`, `validate_manual_workout`, `build_entry` /
/// `build_sync_payload`, `manual_sync_record_id`). The payload wire format is
/// pinned by a cross-language fixture shared with the Python side
/// (`test/models/manual_workout_test.dart` and its twin
/// `test_manual_workout.py::TestSyncWireFormat`) — keep the two in lockstep.
library;

import 'package:crdt_sync/crdt_sync.dart';

part 'manual_workout_budget.dart';
part 'manual_workout_sync.dart';
part 'manual_workout_validation.dart';

// ── Shared constants ─────────────────────────────────────────────────────────
// Hand-maintained mirror of the Python source of truth in
// `screen_locker/_constants.py` (the `MANUAL_WORKOUT_*` values).
//
// The payload fixture does NOT pin these: the caps never travel on the wire,
// so it cannot see them drift — and they did (298daf0 raised Python 5 -> 10
// touching no Dart, leaving the phone at 5). The actual tripwire is
// `TestCrossLanguageBudgetConstants` in
// `screen_locker/tests/test_manual_workout_features.py`, which parses THIS
// file and compares it to the Python constants, so either side drifting fails.

/// Max manual workouts allowed in any rolling 7-day window.
const int kManualWorkoutBudgetPer7Days = 2;

/// Max manual workouts allowed in any rolling 30-day window.
const int kManualWorkoutBudgetPer30Days = 10;

/// The ONE duration bar every workout type answers to, in minutes. This is
/// the ADVERTISED number — the only one that may appear in a message the user
/// reads. Mirrors `MIN_WORKOUT_DURATION_MINUTES` in the locker's
/// `_constants.py`; the two must move together.
const int kMinWorkoutDurationMinutes = 40;

/// The leeway that is deliberately INVISIBLE. A session is accepted at
/// [kMinWorkoutDurationMinutes] minus this, so 35 minutes passes while every
/// string still says 40. That gap is intentional: do NOT "fix" it by
/// advertising the real cutoff, and never interpolate
/// [kWorkoutDurationAcceptMinutes] into a user-facing string.
const int kWorkoutDurationLeewayMinutes = 5;

/// Derived so the advertised and accept bars cannot drift apart. Comparisons
/// use this; messages use [kMinWorkoutDurationMinutes]. Compare with `>=`,
/// matching the locker, so 35.0 cannot pass one side and fail the other.
const int kWorkoutDurationAcceptMinutes =
    kMinWorkoutDurationMinutes - kWorkoutDurationLeewayMinutes;

/// Minimum characters for the "other sport" activity description.
const int kManualWorkoutDescriptionMinChars = 40;

/// Minimum characters required in each reflection field.
const int kManualWorkoutReflectionMinChars = 20;

/// Lowest valid RPE (rate of perceived exertion).
const int kManualWorkoutRpeMin = 1;

/// Highest valid RPE (rate of perceived exertion).
const int kManualWorkoutRpeMax = 10;

/// Record `kind` discriminator marking a manual-workout sync record.
///
/// A StrongLifts session payload has no `kind`; the ingesting PC routes on this
/// value before any session logic, so a manual can never be stamped verified.
const String kManualWorkoutSyncKind = 'manual_workout';

/// Internal sport code for table tennis (structured score fields).
const String kSportTableTennis = 'table_tennis';

/// Internal sport code for any other sport (free-text activity fields).
const String kSportOther = 'other';

/// The sport codes a manual workout may use.
const List<String> kSportChoices = [kSportTableTennis, kSportOther];

/// Human labels for the sport codes, in menu order.
const Map<String, String> kSportLabels = {
  kSportTableTennis: 'Table tennis',
  kSportOther: 'Other',
};

/// User-supplied evidence fields for a manual (unverified) workout.
///
/// Fields shared by every sport come first; the sport-specific groups follow —
/// only the group matching [sport] is validated/persisted.
class ManualWorkoutDraft {
  /// Creates a manual-workout draft.
  const ManualWorkoutDraft({
    required this.sport,
    required this.startTime,
    required this.endTime,
    required this.locationName,
    required this.transportMethod,
    required this.cost,
    required this.rpe,
    required this.wentWell,
    required this.toImprove,
    required this.overallFeeling,
    this.reservationPhone = '',
    this.techniquesPracticed = '',
    this.warmUpMinutes = '',
    this.painOrInjury = 'none',
    this.matchesWon = 0,
    this.matchesLost = 0,
    this.setsWon = 0,
    this.setsLost = 0,
    this.racket = '',
    this.balls = '',
    this.activityTypeOther = '',
    this.activityDetails = '',
    this.equipment = '',
  });

  /// Sport code (see [kSportChoices]).
  final String sport;

  /// Start time as `HH:MM`.
  final String startTime;

  /// End time as `HH:MM`.
  final String endTime;

  /// Where the session happened.
  final String locationName;

  /// How the user travelled there.
  final String transportMethod;

  /// Session cost (free text, e.g. `40 PLN`).
  final String cost;

  /// Rate of perceived exertion (1-10).
  final int rpe;

  /// Reflection: what went well.
  final String wentWell;

  /// Reflection: what to improve.
  final String toImprove;

  /// Reflection: overall feeling.
  final String overallFeeling;

  /// Optional reservation phone number.
  final String reservationPhone;

  /// Optional techniques/focus areas practised.
  final String techniquesPracticed;

  /// Optional warm-up duration (free text).
  final String warmUpMinutes;

  /// Pain or injury notes (defaults to `none`).
  final String painOrInjury;

  /// Table tennis: matches won.
  final int matchesWon;

  /// Table tennis: matches lost.
  final int matchesLost;

  /// Table tennis: sets won.
  final int setsWon;

  /// Table tennis: sets lost.
  final int setsLost;

  /// Table tennis: racket used.
  final String racket;

  /// Table tennis: balls used.
  final String balls;

  /// Other sport: what activity it was.
  final String activityTypeOther;

  /// Other sport: description of what was done.
  final String activityDetails;

  /// Other sport: equipment used.
  final String equipment;
}


/// Builds the persisted `workout_data` dict for a validated draft.
///
/// Byte-for-byte equivalent of the Python `build_entry`.
Map<String, Object?> buildEntry(ManualWorkoutDraft draft) {
  final duration = durationMinutes(draft);
  final activityLabel = draft.sport == kSportTableTennis
      ? 'table tennis'
      : draft.activityTypeOther.trim();

  final entry = <String, Object?>{
    'type': kManualWorkoutSyncKind,
    'source': '$activityLabel at ${draft.locationName.trim()}',
    'sport': draft.sport,
    'activity_type': activityLabel,
    'start_time': draft.startTime.trim(),
    'end_time': draft.endTime.trim(),
    'duration_minutes': duration != null ? duration.toStringAsFixed(1) : '',
    'location_name': draft.locationName.trim(),
    'transport_method': draft.transportMethod.trim(),
    'cost': draft.cost.trim(),
    'reservation_phone': draft.reservationPhone.trim(),
    'rpe': draft.rpe,
    'techniques_practiced': draft.techniquesPracticed.trim(),
    'warm_up_minutes': draft.warmUpMinutes.trim(),
    'pain_or_injury': draft.painOrInjury.trim(),
    'went_well': draft.wentWell.trim(),
    'to_improve': draft.toImprove.trim(),
    'overall_feeling': draft.overallFeeling.trim(),
  };
  if (draft.sport == kSportTableTennis) {
    entry.addAll(<String, Object?>{
      'matches_won': draft.matchesWon,
      'matches_lost': draft.matchesLost,
      'sets_won': draft.setsWon,
      'sets_lost': draft.setsLost,
      'racket': draft.racket.trim(),
      'balls': draft.balls.trim(),
    });
  } else {
    entry.addAll(<String, Object?>{
      'activity_details': draft.activityDetails.trim(),
      'equipment': draft.equipment.trim(),
    });
  }
  return entry;
}
