import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';

// Builds a VALID table-tennis draft; override individual fields per test.
ManualWorkoutDraft _tt({
  String sport = kSportTableTennis,
  String startTime = '18:00',
  String endTime = '19:30',
  String locationName = 'Solec',
  String transportMethod = 'bike',
  String cost = '40 PLN',
  int rpe = 6,
  String wentWell = 'Served consistently and moved feet well',
  String toImprove = 'Backhand topspin needs more consistency',
  String overallFeeling = 'Felt strong focused and in good rhythm',
  int matchesWon = 3,
  int matchesLost = 1,
  int setsWon = 7,
  int setsLost = 4,
  String racket = 'Butterfly',
  String balls = 'Nittaku 3-star',
}) => ManualWorkoutDraft(
  sport: sport,
  startTime: startTime,
  endTime: endTime,
  locationName: locationName,
  transportMethod: transportMethod,
  cost: cost,
  rpe: rpe,
  wentWell: wentWell,
  toImprove: toImprove,
  overallFeeling: overallFeeling,
  matchesWon: matchesWon,
  matchesLost: matchesLost,
  setsWon: setsWon,
  setsLost: setsLost,
  racket: racket,
  balls: balls,
);

// Builds a VALID "other sport" draft; override individual fields per test.
ManualWorkoutDraft _other({
  String activityTypeOther = 'squash',
  String activityDetails =
      'Full-court squash drills and three practice games total',
  String equipment = 'racket, goggles',
}) => ManualWorkoutDraft(
  sport: kSportOther,
  startTime: '09:00',
  endTime: '10:00',
  locationName: 'Squash club',
  transportMethod: 'car',
  cost: '30 PLN',
  rpe: 5,
  wentWell: 'Moved well and kept long rallies going',
  toImprove: 'Need to volley earlier off the back wall',
  overallFeeling: 'Tired but satisfied with the effort',
  activityTypeOther: activityTypeOther,
  activityDetails: activityDetails,
  equipment: equipment,
);

// The cross-language wire fixture — an IDENTICAL literal lives in the Python
// suite (test_manual_workout.py::TestSyncWireFormat). Neither side's own
// round-trip test catches a key-name/format drift from the other; this shared
// literal on both sides does. Change one, change the other.
const _wireDate = '2026-07-13';
const _wirePayload = <String, Object?>{
  'type': 'manual_workout',
  'source': 'table tennis at Solec',
  'sport': 'table_tennis',
  'activity_type': 'table tennis',
  'start_time': '18:00',
  'end_time': '19:30',
  'duration_minutes': '90.0',
  'location_name': 'Solec',
  'transport_method': 'bike',
  'cost': '40 PLN',
  'reservation_phone': '600100200',
  'rpe': 6,
  'techniques_practiced': 'topspin serve',
  'warm_up_minutes': '10',
  'pain_or_injury': 'none',
  'went_well': 'Served consistently and moved feet well',
  'to_improve': 'Backhand topspin needs more consistency',
  'overall_feeling': 'Felt strong focused and in good rhythm',
  'matches_won': 3,
  'matches_lost': 1,
  'sets_won': 7,
  'sets_lost': 4,
  'racket': 'Butterfly',
  'balls': 'Nittaku 3-star',
  'kind': 'manual_workout',
  'date': '2026-07-13',
};

void main() {
  group('cross-language wire format', () {
    // Matches the _wire draft used to produce _wirePayload on the Python side.
    final wireDraft = _tt(
      // These optional fields aren't in _tt's parameter list; set via a fresh
      // draft below so the fixture is exact.
    );

    test('buildSyncPayload matches the shared fixture', () {
      const draft = ManualWorkoutDraft(
        sport: kSportTableTennis,
        startTime: '18:00',
        endTime: '19:30',
        locationName: 'Solec',
        transportMethod: 'bike',
        cost: '40 PLN',
        rpe: 6,
        wentWell: 'Served consistently and moved feet well',
        toImprove: 'Backhand topspin needs more consistency',
        overallFeeling: 'Felt strong focused and in good rhythm',
        reservationPhone: '600100200',
        techniquesPracticed: 'topspin serve',
        warmUpMinutes: '10',
        matchesWon: 3,
        matchesLost: 1,
        setsWon: 7,
        setsLost: 4,
        racket: 'Butterfly',
        balls: 'Nittaku 3-star',
      );
      expect(buildSyncPayload(draft, _wireDate), _wirePayload);
    });

    test('record id is stable and prefixed', () {
      expect(manualSyncRecordId(_wireDate, '18:00'), 'manual:2026-07-13T18:00');
    });

    test('buildManualRecord wraps the payload under a manual id', () {
      final record = buildManualRecord(
        wireDraft,
        _wireDate,
        hlc: Hlc.newTick('phone'),
      );
      expect(record.id, 'manual:2026-07-13T18:00');
      expect(record.fields['payload']!.$1, buildSyncPayload(wireDraft, _wireDate));
    });
  });

  group('validateManualWorkout', () {
    test('valid table tennis returns null', () {
      expect(validateManualWorkout(_tt()), isNull);
    });

    test('valid other sport returns null', () {
      expect(validateManualWorkout(_other()), isNull);
    });

    test('rejects an unknown sport', () {
      expect(validateManualWorkout(_tt(sport: 'badminton')), isNotNull);
    });

    for (final field in ['start', 'end', 'location', 'transport', 'cost']) {
      test('rejects blank $field', () {
        final draft = switch (field) {
          'start' => _tt(startTime: '  '),
          'end' => _tt(endTime: '  '),
          'location' => _tt(locationName: '  '),
          'transport' => _tt(transportMethod: '  '),
          _ => _tt(cost: '  '),
        };
        expect(validateManualWorkout(draft), isNotNull);
      });
    }

    test('rejects a bad time format', () {
      expect(validateManualWorkout(_tt(startTime: 'noon')), isNotNull);
    });

    test('rejects end not after start', () {
      expect(
        validateManualWorkout(_tt(startTime: '14:00', endTime: '12:00')),
        isNotNull,
      );
    });

    test('rejects an out-of-range hour', () {
      expect(validateManualWorkout(_tt(startTime: '25:00')), isNotNull);
    });

    test('rejects a too-short session', () {
      expect(
        validateManualWorkout(_tt(startTime: '12:00', endTime: '12:05')),
        isNotNull,
      );
    });

    test('rejects an out-of-range RPE', () {
      expect(validateManualWorkout(_tt(rpe: 0)), isNotNull);
      expect(validateManualWorkout(_tt(rpe: 11)), isNotNull);
    });

    test('rejects a short reflection', () {
      expect(validateManualWorkout(_tt(wentWell: 'ok')), isNotNull);
    });
  });

  group('table tennis validation', () {
    test('rejects a negative score', () {
      expect(validateManualWorkout(_tt(matchesWon: -1)), isNotNull);
    });

    test('rejects zero matches played', () {
      expect(
        validateManualWorkout(_tt(matchesWon: 0, matchesLost: 0)),
        isNotNull,
      );
    });

    test('requires a racket', () {
      expect(validateManualWorkout(_tt(racket: '  ')), isNotNull);
    });

    test('requires balls', () {
      expect(validateManualWorkout(_tt(balls: '  ')), isNotNull);
    });
  });

  group('other sport validation', () {
    test('requires an activity type', () {
      expect(validateManualWorkout(_other(activityTypeOther: '  ')), isNotNull);
    });

    test('requires a long-enough description', () {
      expect(validateManualWorkout(_other(activityDetails: 'short')), isNotNull);
    });
  });

  group('buildEntry', () {
    test('table tennis carries score fields and a table-tennis label', () {
      final entry = buildEntry(_tt());
      expect(entry['activity_type'], 'table tennis');
      expect(entry['matches_lost'], 1);
      expect(entry['source'], 'table tennis at Solec');
    });

    test('other sport carries description/equipment and its own label', () {
      final entry = buildEntry(_other());
      expect(entry['activity_type'], 'squash');
      expect(entry['activity_details'], contains('squash'));
      expect(entry['equipment'], 'racket, goggles');
    });

    test('duration is empty for an unparsable time', () {
      expect(buildEntry(_tt(startTime: 'bogus'))['duration_minutes'], '');
    });

    test('strips whitespace from fields', () {
      final entry = buildEntry(_tt(locationName: '  Solec  ', racket: '  pro '));
      expect(entry['location_name'], 'Solec');
      expect(entry['racket'], 'pro');
    });
  });

  group('durationMinutes', () {
    test('returns minutes for a valid range', () {
      expect(durationMinutes(_tt(startTime: '12:00', endTime: '13:30')), 90.0);
    });

    test('returns null for an unparsable time', () {
      expect(durationMinutes(_tt(startTime: 'noon')), isNull);
    });
  });
}
