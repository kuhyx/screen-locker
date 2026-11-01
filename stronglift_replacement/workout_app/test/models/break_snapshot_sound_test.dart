// The snapshot carries the user's sound choice across the isolate boundary:
// the service isolate cannot read the settings table, so it must be told.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_snapshot.dart';

import '../services/_break_task_handler_fixtures.dart';

void main() {
  test('sound is on unless the snapshot says otherwise', () {
    final map = snapMap();
    expect(BreakSnapshot.tryFromMap(map)!.soundOn, isTrue);
    map.remove('soundOn');
    expect(
      BreakSnapshot.tryFromMap(map)!.soundOn,
      isTrue,
      reason: 'an older UI that never sent the key must not go silent',
    );
  });

  test('an explicit off survives the trip', () {
    final map = snapMap(soundOn: false);
    expect(map['soundOn'], false);
    final back = BreakSnapshot.tryFromMap(map)!;
    expect(back.soundOn, isFalse);
    expect(back.copyWith(setsRemaining: 1).soundOn, isFalse);
  });
}
