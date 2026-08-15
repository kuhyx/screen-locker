@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';

/// Cross-language fixture test for the unified workout-duration gate.
///
/// The locker mirrors these constants in `screen_locker/_constants.py`. Each
/// language's own round-trip test passes happily while the two sides
/// disagree, so the only thing that catches a drift is a shared literal both
/// read. The Python twin of this file is
/// `screen_locker/tests/test_duration_threshold_fixture.py`.
///
/// The fixture lives in the locker's test tree because that is the side that
/// owns the gate; this app reads it up four directories.
final File _fixtureFile = File(
  '../../screen_locker/tests/fixtures/duration_threshold.json',
);

Map<String, dynamic> _fixture() =>
    jsonDecode(_fixtureFile.readAsStringSync()) as Map<String, dynamic>;

/// Builds an otherwise-valid "other sport" draft of exactly [durationMinutes].
ManualWorkoutDraft _draft(int durationMinutes) {
  final totalMinutes = 12 * 60 + durationMinutes;
  final endH = (totalMinutes ~/ 60).toString().padLeft(2, '0');
  final endM = (totalMinutes % 60).toString().padLeft(2, '0');
  return ManualWorkoutDraft(
    sport: kSportOther,
    startTime: '12:00',
    endTime: '$endH:$endM',
    locationName: 'Home',
    transportMethod: 'From bed',
    cost: '0',
    rpe: 3,
    wentWell: 'Everything went smoothly today, no issues at all',
    toImprove: 'Dumbbell bench press needs assistance exercises',
    overallFeeling: 'Felt strong throughout the whole session today',
    reservationPhone: 'none',
    techniquesPracticed: 'FBW',
    warmUpMinutes: 'none',
    painOrInjury: 'none',
    activityTypeOther: 'Weightlifting',
    activityDetails: 'Dumbbell Lunge, Press, Row and Dumbbell Curl at home',
    equipment: 'Dumbbells',
  );
}

void main() {
  test('the shared fixture exists where both languages can read it', () {
    expect(
      _fixtureFile.existsSync(),
      isTrue,
      reason: 'Shared threshold fixture missing at ${_fixtureFile.path}',
    );
  });

  test('Dart constants match the shared literal the locker also reads', () {
    final data = _fixture();
    expect(kMinWorkoutDurationMinutes, data['advertised_minutes']);
    expect(kWorkoutDurationLeewayMinutes, data['leeway_minutes']);
    expect(kWorkoutDurationAcceptMinutes, data['accept_minutes']);
  });

  test('the accept bar is derived, not hardcoded', () {
    expect(
      kWorkoutDurationAcceptMinutes,
      kMinWorkoutDurationMinutes - kWorkoutDurationLeewayMinutes,
    );
  });

  test('every shared boundary case decides the same way here', () {
    for (final dynamic entry in _fixture()['cases'] as List<dynamic>) {
      final c = entry as Map<String, dynamic>;
      final minutes = c['duration_minutes'] as int;
      final shouldAccept = c['accepted'] as bool;
      final error = validateManualWorkout(_draft(minutes));
      expect(
        error == null,
        shouldAccept,
        reason:
            '$minutes min should be ${shouldAccept ? "accepted" : "rejected"}, '
            'got $error',
      );
    }
  });

  test('the rejection message advertises 40 and never the real cutoff', () {
    final error = validateManualWorkout(_draft(10));
    expect(error, isNotNull);
    expect(error, contains('$kMinWorkoutDurationMinutes'));
    expect(error, isNot(contains('$kWorkoutDurationAcceptMinutes')));
  });
}
