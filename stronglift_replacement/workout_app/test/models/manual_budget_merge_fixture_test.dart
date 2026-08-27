@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';

/// Cross-language fixture test for manual-workout budget counting.
///
/// The locker mirrors this accounting in `screen_locker/_manual_workout.py`
/// and `screen_locker/_sync_records.py`. Each language's own round-trip test
/// passed happily while the two sides disagreed -- on 2026-08-27 this phone
/// read `2/2w 4/10m (exhausted)` for the very records the PC read as
/// `1/2w 2/10m` -- so the only thing that catches the drift is a shared
/// literal both read. The Python twin is
/// `screen_locker/tests/test_manual_budget_merge_fixture.py`.
///
/// The fixture lives in the locker's test tree because that is the side that
/// owns the budget; this app reads it up four directories.
final File _fixtureFile = File(
  '../../screen_locker/tests/fixtures/manual_budget_merge.json',
);

Map<String, dynamic> _fixture() =>
    jsonDecode(_fixtureFile.readAsStringSync()) as Map<String, dynamic>;

/// Rebuilds the fixture as a device log, exactly as a sync backend serves it.
///
/// Going through `Record`/`Log` rather than handing the payloads straight to
/// the counter is the point: the tombstone that caused the incident only
/// exists at the record layer, so a test that skipped it could not fail.
String _deviceLogJson(List<dynamic> records) {
  final hlc = Hlc.fromStr('2026-08-27T00:00:00.000Z-0000-fixture');
  final log = <String, Record>{
    for (final entry in records.cast<Map<String, dynamic>>())
      entry['id'] as String: Record(
        id: entry['id'] as String,
        fields: {'payload': (entry['payload'], hlc)},
        deleted: entry['deleted'] as bool,
        deletedHlc: (entry['deleted'] as bool) ? hlc : null,
      ),
  };
  return jsonEncode(log.map((id, r) => MapEntry(id, r.toJson())));
}

/// Applies the same union-wide suppression the reader does.
List<Map<String, dynamic>> _livePayloads(String logJson) {
  final raw = jsonDecode(logJson) as Map<String, dynamic>;
  final live = <Map<String, dynamic>>[];
  for (final data in raw.values) {
    final record = Record.fromJson(data as Map<String, dynamic>);
    if (record.deleted) continue;
    final payload = record.fields['payload']?.$1;
    if (payload is Map) live.add(payload.cast<String, dynamic>());
  }
  return live;
}

void main() {
  test('budget matches the locker for the 2026-08-27 divergence', () {
    final fixture = _fixture();
    final expected = fixture['expected'] as Map<String, dynamic>;
    final today = DateTime.parse(fixture['today'] as String);

    final payloads = _livePayloads(
      _deviceLogJson(fixture['records'] as List<dynamic>),
    );
    final budget = countManualBudget(payloads, today);

    expect(budget.week, expected['week']);
    expect(budget.month, expected['month']);
    expect(budget.exhausted, expected['exhausted']);
  });

  test('a tombstoned duplicate frees its weekly slot', () {
    final fixture = _fixture();
    final records = fixture['records'] as List<dynamic>;
    final today = DateTime.parse(fixture['today'] as String);

    // Resurrecting the deleted duplicate is precisely the pre-fix behaviour:
    // it must push the week to the cap, proving the tombstone is load-bearing
    // rather than incidentally absent from the window.
    final resurrected = [
      for (final entry in records.cast<Map<String, dynamic>>())
        {...entry, 'deleted': false},
    ];
    final budget = countManualBudget(
      _livePayloads(_deviceLogJson(resurrected)),
      today,
    );

    expect(budget.week, 2);
    expect(budget.exhausted, isTrue);
  });

  test('an evidence-less stub never consumes budget', () {
    final fixture = _fixture();
    final today = DateTime.parse(fixture['today'] as String);
    final stub = (fixture['records'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .firstWhere((e) => !(e['payload'] as Map).containsKey('start_time'));

    final budget = countManualBudget([
      (stub['payload'] as Map).cast<String, dynamic>(),
    ], today);

    expect(budget.week, 0);
    expect(budget.month, 0);
  });
}
