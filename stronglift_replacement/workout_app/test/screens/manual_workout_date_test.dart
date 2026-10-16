// The workout date on the manual form: today up to a week ahead, the budget
// read as of that date, and the refusals around it.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/services/workout_sync_service.dart';

import '_manual_screen_fixtures.dart';

void main() {
  group('workout date', () {
    testWidgets('a future date is pushed under that date', (tester) async {
      final sync = FakeManualSync();
      await pumpManual(
        tester,
        ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
      );
      await pickDay(tester, '14');
      expect(find.text('Workout date: 2026-07-14 (tomorrow)'), findsOneWidget);
      await fillValidTt(tester);
      await tester.tap(find.text('SUBMIT'));
      await tester.pumpAndSettle();
      expect(sync.pushed!.id, 'manual:2026-07-14T18:00');
      final payload = sync.pushed!.fields['payload']!.$1! as Map;
      expect(payload['date'], '2026-07-14');
    });

    testWidgets('the picker offers today to today+7 only', (tester) async {
      await pumpManual(
        tester,
        ManualWorkoutScreen(
          syncService: FakeManualSync(),
          clock: fixedManualNow,
        ),
      );
      await tester.tap(find.text('CHANGE DATE'));
      await tester.pumpAndSettle();
      final picker = tester.widget<DatePickerDialog>(
        find.byType(DatePickerDialog),
      );
      expect(picker.firstDate, DateTime(2026, 7, 13));
      expect(picker.lastDate, DateTime(2026, 7, 20));
      expect(picker.initialDate, DateTime(2026, 7, 13));
      await tester.tap(find.text('20'));
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      expect(find.text('Workout date: 2026-07-20 (in 7 days)'), findsOneWidget);
    });

    testWidgets('cancelling the picker keeps the date', (tester) async {
      await pumpManual(
        tester,
        ManualWorkoutScreen(
          syncService: FakeManualSync(),
          clock: fixedManualNow,
        ),
      );
      await tester.tap(find.text('CHANGE DATE'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.text('Workout date: 2026-07-13 (today)'), findsOneWidget);
    });

    testWidgets('the budget follows the selected date', (tester) async {
      // 07-12 and a planned 07-18 share the window 07-12..07-18, which
      // contains today: today is full, 07-20 is not.
      await pumpManual(
        tester,
        ManualWorkoutScreen(
          syncService: FakeManualSync(
            payloads: [manualEntry('2026-07-12'), manualEntry('2026-07-18')],
          ),
          clock: fixedManualNow,
        ),
      );
      expect(find.textContaining('2/2 per 7 days'), findsOneWidget);
      expect(find.textContaining('budget exhausted'), findsOneWidget);
      expect(find.text('SUBMIT'), findsNothing);
      // The date row stays reachable while the window is full.
      await pickDay(tester, '20');
      expect(
        find.text(
          'Manual around 2026-07-20: 1/2 per 7 days · 2/10 per 30 days',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('budget exhausted'), findsNothing);
      expect(find.text('SUBMIT'), findsOneWidget);
    });

    testWidgets('re-logging onto a deleted record is refused', (tester) async {
      final sync = FakeManualSync(tombstoned: {'manual:2026-07-13T18:00'});
      await pumpManual(
        tester,
        ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
      );
      await fillValidTt(tester);
      await tester.tap(find.text('SUBMIT'));
      await tester.pump();
      expect(find.textContaining('was deleted earlier'), findsOneWidget);
      expect(sync.pushed, isNull);
      // A different start time is a different record id.
      await tester.enterText(find.byKey(const Key('mw_start_time')), '17:30');
      await tester.tap(find.text('SUBMIT'));
      await tester.pumpAndSettle();
      expect(sync.pushed!.id, 'manual:2026-07-13T17:30');
    });

    testWidgets('a failed push keeps the form open and says why', (
      tester,
    ) async {
      final sync = FakeManualSync(
        result: const PushResult(pushed: false, reason: 'push failed: 500'),
      );
      await pumpManual(
        tester,
        ManualWorkoutScreen(syncService: sync, clock: fixedManualNow),
      );
      await fillValidTt(tester);
      await tester.tap(find.text('SUBMIT'));
      await tester.pumpAndSettle();
      expect(sync.pushed, isNotNull);
      expect(find.text('Not saved — push failed: 500'), findsOneWidget);
      expect(find.text('Log Manual Workout'), findsOneWidget);
      final submit = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'SUBMIT'),
      );
      expect(submit.onPressed, isNotNull);
    });

    testWidgets('a date left behind by midnight is refused, then clamped', (
      tester,
    ) async {
      var now = DateTime(2026, 7, 13, 23, 59);
      final sync = FakeManualSync();
      await pumpManual(
        tester,
        ManualWorkoutScreen(syncService: sync, clock: () => now),
      );
      await fillValidTt(tester);
      now = DateTime(2026, 7, 14, 0, 1);
      await tester.tap(find.text('SUBMIT'));
      await tester.pump();
      expect(find.textContaining('is in the past'), findsOneWidget);
      expect(sync.pushed, isNull);
      // The picker would assert on an initial date before its range.
      await tester.tap(find.text('CHANGE DATE'));
      await tester.pumpAndSettle();
      final picker = tester.widget<DatePickerDialog>(
        find.byType(DatePickerDialog),
      );
      expect(picker.initialDate, DateTime(2026, 7, 14));
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      expect(find.text('Workout date: 2026-07-14 (today)'), findsOneWidget);
    });

    testWidgets('a date beyond the window is refused at submit', (
      tester,
    ) async {
      // Only a clock moving backwards can get here; refuse rather than push.
      var now = DateTime(2026, 7, 13, 12);
      final sync = FakeManualSync();
      await pumpManual(
        tester,
        ManualWorkoutScreen(syncService: sync, clock: () => now),
      );
      await pickDay(tester, '20');
      await fillValidTt(tester);
      now = DateTime(2026, 7, 12, 12);
      await tester.tap(find.text('SUBMIT'));
      await tester.pump();
      expect(find.textContaining('at most 7 days ahead'), findsOneWidget);
      expect(sync.pushed, isNull);
    });
  });
}
