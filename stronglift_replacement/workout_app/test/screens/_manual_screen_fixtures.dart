// Shared fixtures for the manual-workout form tests.
//
// Hoisted to top level so the split test files import one definition (see
// _history_test_fixtures.dart for why local copies drift).
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/workout_sync_service.dart';

class FakeManualSync extends WorkoutSyncService {
  FakeManualSync({
    this.payloads = const [],
    this.tombstoned = const {},
    this.result = const PushResult(pushed: true, reason: 'pushed'),
  });

  final List<Map<String, dynamic>> payloads;
  final Set<String> tombstoned;
  final PushResult result;
  Record? pushed;

  @override
  Future<ManualLedger> readManualLedger() async =>
      (payloads: payloads, tombstoned: tombstoned);

  @override
  Future<PushResult> pushManual(Record record) async {
    pushed = record;
    return result;
  }
}

Map<String, dynamic> manualEntry(String date) => {
  'kind': 'manual_workout',
  'date': date,
  'start_time': '18:00',
  'end_time': '19:00',
};

/// Opens the date picker, taps [day] of the shown month, confirms.
Future<void> pickDay(WidgetTester tester, String day) async {
  await tester.tap(find.text('CHANGE DATE'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(day));
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

DateTime fixedManualNow() => DateTime(2026, 7, 13, 20);

Future<void> pumpManual(WidgetTester tester, Widget child) async {
  // Tall viewport so the whole (long) form is laid out — a ListView only builds
  // children within the viewport, so off-screen widgets aren't findable.
  tester.view.physicalSize = const Size(500, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle(); // let the budget future resolve
}

Future<void> fillValidTt(WidgetTester tester) async {
  Future<void> enter(String key, String value) =>
      tester.enterText(find.byKey(Key('mw_$key')), value);
  await enter('start_time', '18:00');
  await enter('end_time', '19:30');
  await enter('location_name', 'Solec');
  await enter('transport_method', 'bike');
  await enter('cost', '40 PLN');
  await enter('matches_won', '3');
  await enter('matches_lost', '1');
  await enter('sets_won', '7');
  await enter('sets_lost', '4');
  await enter('racket', 'Butterfly');
  await enter('balls', 'Nittaku');
  await enter('pain_or_injury', 'sore knee');
  await enter('went_well', 'Served consistently and moved feet well');
  await enter('to_improve', 'Backhand topspin needs more consistency');
  await enter('overall_feeling', 'Felt strong focused and in good rhythm');
}
