// The tombstone that deletes a planned manual workout on every device.
//
// Split from manual_workout_test.dart for the 250-line cap.
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';

const _draft = ManualWorkoutDraft(
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
);

void main() {
  test('buildManualTombstone is a field-less, deleted record', () {
    final hlc = Hlc.newTick('phone');
    final tombstone = buildManualTombstone('manual:2026-07-13T18:00', hlc: hlc);
    expect(tombstone.id, 'manual:2026-07-13T18:00');
    expect(tombstone.fields, isEmpty);
    expect(tombstone.deleted, isTrue);
    expect(tombstone.deletedHlc, hlc);
    // Merged onto the live record it keeps the payload and stays deleted.
    final live = buildManualRecord(_draft, '2026-07-13', hlc: hlc);
    final merged = mergeRecord(live, tombstone);
    expect(merged.deleted, isTrue);
    expect(merged.fields['payload'], live.fields['payload']);
    expect(tombstone.toJson()['deleted_hlc'], hlc.toStr());
  });
}
