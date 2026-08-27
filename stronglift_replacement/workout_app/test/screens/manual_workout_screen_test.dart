import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/services/workout_sync_service.dart';

class _FakeSync extends WorkoutSyncService {
  _FakeSync({this.payloads = const []});

  final List<Map<String, dynamic>> payloads;
  Record? pushed;

  @override
  Future<List<Map<String, dynamic>>> readMergedManualPayloads() async =>
      payloads;

  @override
  Future<PushResult> pushManual(Record record) async {
    pushed = record;
    return const PushResult(pushed: true, reason: 'pushed');
  }
}

DateTime _fixedNow() => DateTime(2026, 7, 13, 20);

Future<void> _pump(WidgetTester tester, Widget child) async {
  // Tall viewport so the whole (long) form is laid out — a ListView only builds
  // children within the viewport, so off-screen widgets aren't findable.
  tester.view.physicalSize = const Size(500, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle(); // let the budget future resolve
}

Future<void> _fillValidTt(WidgetTester tester) async {
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

void main() {
  testWidgets('shows the form and budget when not exhausted', (tester) async {
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: _FakeSync(), clock: _fixedNow),
    );
    expect(find.text('Log Manual Workout'), findsOneWidget);
    expect(find.text('SUBMIT'), findsOneWidget);
    expect(find.textContaining('0/2 this week'), findsOneWidget);
  });

  testWidgets('hides the form when the budget is exhausted', (tester) async {
    // Real self-reports, not bare {kind, date} stubs: the counter ignores
    // payloads with no `start_time`, because the PC refuses to ingest those
    // and a budget must not be spent on a workout neither device accepted.
    final payloads = [
      {
        'kind': 'manual_workout',
        'date': '2026-07-12',
        'start_time': '18:00',
        'end_time': '19:00',
      },
      {
        'kind': 'manual_workout',
        'date': '2026-07-13',
        'start_time': '18:00',
        'end_time': '19:00',
      },
    ];
    await _pump(
      tester,
      ManualWorkoutScreen(
        syncService: _FakeSync(payloads: payloads),
        clock: _fixedNow,
      ),
    );
    expect(find.textContaining('budget exhausted'), findsOneWidget);
    expect(find.text('SUBMIT'), findsNothing);
  });

  testWidgets('shows a validation error and does not push', (tester) async {
    final sync = _FakeSync();
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: _fixedNow),
    );
    await tester.tap(find.text('SUBMIT'));
    await tester.pump();
    expect(find.textContaining('is required'), findsOneWidget);
    expect(sync.pushed, isNull);
  });

  testWidgets('valid table-tennis workout pushes and pops', (tester) async {
    final sync = _FakeSync();
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: _fixedNow),
    );
    await _fillValidTt(tester);
    await tester.tap(find.text('SUBMIT'));
    await tester.pumpAndSettle();
    expect(sync.pushed, isNotNull);
    expect(sync.pushed!.id, 'manual:2026-07-13T18:00');
    final payload = sync.pushed!.fields['payload']!.$1! as Map;
    expect(payload['kind'], 'manual_workout');
    expect(payload['matches_won'], 3);
  });

  testWidgets('switching sport reveals the other-sport fields', (tester) async {
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: _FakeSync(), clock: _fixedNow),
    );
    expect(find.byKey(const Key('mw_matches_won')), findsOneWidget);
    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Other').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('mw_activity_type_other')), findsOneWidget);
    expect(find.byKey(const Key('mw_matches_won')), findsNothing);
  });

  testWidgets('RPE slider updates the label', (tester) async {
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: _FakeSync(), clock: _fixedNow),
    );
    expect(find.text('RPE 5'), findsOneWidget);
    await tester.drag(find.byType(Slider), const Offset(300, 0));
    await tester.pump();
    expect(find.text('RPE 5'), findsNothing);
  });

  testWidgets('other-sport validation error pushes nothing', (tester) async {
    final sync = _FakeSync();
    await _pump(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: _fixedNow),
    );
    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Other').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('mw_start_time')), '18:00');
    await tester.enterText(find.byKey(const Key('mw_end_time')), '19:30');
    await tester.enterText(find.byKey(const Key('mw_location_name')), 'Club');
    await tester.enterText(find.byKey(const Key('mw_transport_method')), 'car');
    await tester.enterText(find.byKey(const Key('mw_cost')), '30');
    await tester.tap(find.text('SUBMIT'));
    await tester.pump();
    expect(find.textContaining('Activity type is required'), findsOneWidget);
    expect(sync.pushed, isNull);
  });
}
