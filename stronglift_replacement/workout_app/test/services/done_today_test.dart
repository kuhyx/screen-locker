import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/done_today.dart';

final _day = DateTime(2026, 9, 28, 7, 30);

void main() {
  group('dayKey', () {
    test('zero-pads month and day', () {
      expect(dayKey(DateTime(2026, 3, 4)), '2026-03-04');
    });

    test('ignores the time of day', () {
      expect(dayKey(_day), '2026-09-28');
    });
  });

  group('anyWorkoutOn', () {
    test('a bare day key from the PC log matches', () {
      expect(
        anyWorkoutOn([
          {'kind': 'runnerup_verified', 'date': '2026-09-28'},
        ], _day),
        isTrue,
      );
    });

    test('a full ISO timestamp from a session matches its day', () {
      expect(
        anyWorkoutOn([
          {'date': '2026-09-28T06:05:44.066'},
        ], _day),
        isTrue,
      );
    });

    test('another day does not count', () {
      expect(
        anyWorkoutOn([
          {'date': '2026-09-27'},
          {'date': '2026-09-29T00:01:00'},
        ], _day),
        isFalse,
      );
    });

    test('a record with no date does not count', () {
      expect(
        anyWorkoutOn([
          {'kind': 'manual_workout'},
        ], _day),
        isFalse,
      );
    });

    test('no records at all is not done', () {
      expect(anyWorkoutOn(const [], _day), isFalse);
    });
  });
}
