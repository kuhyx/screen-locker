// Draft validation: duration, per-sport rules, and the shared minimums.
//
// A `part` so the constants and the draft stay one library -- this file is
// a cross-language contract with the Python side, and the JSON keys it
// emits must not move or change.
part of 'manual_workout.dart';

int? _parseHhmm(String value) {
  final match = RegExp(r'^(\d{1,2}):(\d{2})$').firstMatch(value.trim());
  if (match == null) return null;
  final hours = int.parse(match.group(1)!);
  final minutes = int.parse(match.group(2)!);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/// Minutes between start and end, or null if unparsable / not end-after-start.
double? durationMinutes(ManualWorkoutDraft draft) {
  final start = _parseHhmm(draft.startTime);
  final end = _parseHhmm(draft.endTime);
  if (start == null || end == null || end <= start) return null;
  return (end - start).toDouble();
}

/// Returns an error message if [draft] is invalid, else null.
///
/// Ports `validate_manual_workout`: required fields, HH:MM with end after
/// start, minimum duration, RPE range, per-sport rules, and reflection length.
String? validateManualWorkout(ManualWorkoutDraft draft) {
  if (!kSportChoices.contains(draft.sport)) return 'Please choose a sport';

  final required = <String, String>{
    'Start time': draft.startTime,
    'End time': draft.endTime,
    'Location name': draft.locationName,
    'Transport method': draft.transportMethod,
    'Cost': draft.cost,
  };
  for (final entry in required.entries) {
    if (entry.value.trim().isEmpty) return '${entry.key} is required';
  }

  final duration = durationMinutes(draft);
  if (duration == null) {
    return 'Start/end time must be valid HH:MM, with end after start';
  }
  // Accept bar carries the hidden leeway; the message advertises the round
  // number only.
  if (duration < kWorkoutDurationAcceptMinutes) {
    return 'Session must be at least $kMinWorkoutDurationMinutes '
        'minutes (currently ${duration.toStringAsFixed(0)})';
  }

  if (draft.rpe < kManualWorkoutRpeMin || draft.rpe > kManualWorkoutRpeMax) {
    return 'RPE must be between $kManualWorkoutRpeMin '
        'and $kManualWorkoutRpeMax';
  }

  final sportError = draft.sport == kSportTableTennis
      ? _validateTableTennis(draft)
      : _validateOtherSport(draft);
  if (sportError != null) return sportError;

  final reflections = <String, String>{
    'What went well': draft.wentWell,
    'What to improve': draft.toImprove,
    'Overall feeling': draft.overallFeeling,
  };
  for (final entry in reflections.entries) {
    final length = entry.value.trim().length;
    if (length < kManualWorkoutReflectionMinChars) {
      return '${entry.key} must be at least $kManualWorkoutReflectionMinChars '
          'characters (currently $length)';
    }
  }

  return null;
}

String? _validateTableTennis(ManualWorkoutDraft draft) {
  final scores = <String, int>{
    'Matches won': draft.matchesWon,
    'Matches lost': draft.matchesLost,
    'Sets won': draft.setsWon,
    'Sets lost': draft.setsLost,
  };
  for (final entry in scores.entries) {
    if (entry.value < 0) return '${entry.key} cannot be negative';
  }
  if (draft.matchesWon + draft.matchesLost == 0) {
    return 'Enter at least one match played (won + lost)';
  }
  if (draft.racket.trim().isEmpty) return 'Racket is required';
  if (draft.balls.trim().isEmpty) return 'Balls are required';
  return null;
}

String? _validateOtherSport(ManualWorkoutDraft draft) {
  if (draft.activityTypeOther.trim().isEmpty) {
    return 'Activity type is required';
  }
  final length = draft.activityDetails.trim().length;
  if (length < kManualWorkoutDescriptionMinChars) {
    return 'What was done must be at least '
        '$kManualWorkoutDescriptionMinChars characters (currently $length)';
  }
  return null;
}
