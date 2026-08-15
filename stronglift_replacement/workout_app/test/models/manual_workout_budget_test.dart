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
  group('countManualBudget (per-entry)', () {
    Map<String, dynamic> payload(String date, String start) => {
      'date': date,
      'start_time': start,
    };
    final now = DateTime(2026, 7, 16);

    // Was "count as a single day" until 2026-08-09, which disagreed with the
    // PC's count_in_window ("Counted per entry, not per day"): three same-day
    // workouts read 3/2 there — over the 7-day cap — but 1/2 here, so the
    // phone kept accepting what the PC had already refused.
    test('multiple workouts on one day each consume a slot', () {
      final budget = countManualBudget([
        payload('2026-07-13', '14:00'),
        payload('2026-07-13', '23:07'),
      ], now);
      expect(budget.week, 2);
      expect(budget.month, 2);
    });

    test('three on one day exhaust the 7-day cap, matching the PC', () {
      final budget = countManualBudget([
        payload('2026-07-13', '09:00'),
        payload('2026-07-13', '14:00'),
        payload('2026-07-13', '19:00'),
      ], now);
      expect(budget.week, 3);
      expect(budget.week >= kManualWorkoutBudgetPer7Days, isTrue);
    });

    test('workouts on distinct days each count', () {
      final budget = countManualBudget([
        payload('2026-07-13', '14:00'),
        payload('2026-07-15', '09:00'),
      ], now);
      expect(budget.week, 2);
    });

    test('same-day pair plus another day counts three entries', () {
      final budget = countManualBudget([
        payload('2026-07-13', '14:00'),
        payload('2026-07-13', '23:07'),
        payload('2026-07-15', '09:00'),
      ], now);
      expect(budget.week, 3);
    });

    test('ignores dates outside the 30-day window and future dates', () {
      final budget = countManualBudget([
        payload('2026-05-01', '10:00'),
        payload('2026-07-20', '10:00'),
      ], now);
      expect(budget.week, 0);
      expect(budget.month, 0);
    });

    test('skips payloads with missing or unparsable date', () {
      final budget = countManualBudget([
        {'start_time': '10:00'},
        {'date': 42},
        {'date': 'not-a-date'},
      ], now);
      expect(budget.week, 0);
      expect(budget.month, 0);
    });
  });
}
