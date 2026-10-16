import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/services/workout_sync_service.dart';

import '_manual_screen_fixtures.dart';

void main() {
  testWidgets('shows the form and budget when not exhausted', (tester) async {
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: FakeManualSync(), clock: fixedManualNow),
    );
    expect(find.text('Log Manual Workout'), findsOneWidget);
    expect(find.text('SUBMIT'), findsOneWidget);
    expect(
      find.text('Manual around 2026-07-13: 0/2 per 7 days · 0/10 per 30 days'),
      findsOneWidget,
    );
    expect(find.text('Workout date: 2026-07-13 (today)'), findsOneWidget);
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
    await pumpManual(
      tester,
      ManualWorkoutScreen(
        syncService: FakeManualSync(payloads: payloads),
        clock: fixedManualNow,
      ),
    );
    expect(find.textContaining('budget exhausted'), findsOneWidget);
    expect(find.text('SUBMIT'), findsNothing);
  });

  testWidgets('shows a validation error and does not push', (tester) async {
    final sync = FakeManualSync();
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
    );
    await tester.tap(find.text('SUBMIT'));
    await tester.pump();
    expect(find.textContaining('is required'), findsOneWidget);
    expect(sync.pushed, isNull);
  });

  testWidgets('valid table-tennis workout pushes and pops', (tester) async {
    final sync = FakeManualSync();
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
    );
    await fillValidTt(tester);
    await tester.tap(find.text('SUBMIT'));
    await tester.pumpAndSettle();
    expect(sync.pushed, isNotNull);
    expect(sync.pushed!.id, 'manual:2026-07-13T18:00');
    final payload = sync.pushed!.fields['payload']!.$1! as Map;
    expect(payload['kind'], 'manual_workout');
    expect(payload['matches_won'], 3);
  });

  testWidgets('switching sport reveals the other-sport fields', (tester) async {
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: FakeManualSync(), clock: fixedManualNow),
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
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: FakeManualSync(), clock: fixedManualNow),
    );
    expect(find.text('RPE 5'), findsOneWidget);
    await tester.drag(find.byType(Slider), const Offset(300, 0));
    await tester.pump();
    expect(find.text('RPE 5'), findsNothing);
  });

  testWidgets('other-sport validation error pushes nothing', (tester) async {
    final sync = FakeManualSync();
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
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
