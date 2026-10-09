// The "Deload now" row: confirm dialog, host hand-off, re-render.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';

final _bench = ExerciseState.initial(workoutA[1]); // 22.5 kg x 12

Future<void> _pump(
  WidgetTester tester,
  ExerciseState state,
  Future<ExerciseState?> Function() onDeload,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: ExerciseSettingsSheet(
          state: state,
          onChanged: (_) {},
          onDeload: onDeload,
        ),
      ),
    ),
  );
  await tester.ensureVisible(find.text('Deload now'));
  await tester.pump();
}

TextButton _button(WidgetTester tester) =>
    tester.widget<TextButton>(find.widgetWithText(TextButton, 'Deload now'));

void main() {
  testWidgets('the row names the current and the next target', (tester) async {
    await _pump(tester, _bench, () async => null);
    expect(find.text('Deload  22.5 kg × 12 → 20 kg'), findsOneWidget);
    expect(_button(tester).onPressed, isNotNull);
  });

  testWidgets('a whole-kilo weight prints without a decimal', (tester) async {
    await _pump(tester, _bench.copyWith(weight: 20), () async => null);
    expect(find.text('Deload  20 kg × 12 → 17.5 kg'), findsOneWidget);
  });

  testWidgets('confirming deloads and the row shows the next step down', (
    tester,
  ) async {
    var calls = 0;
    await _pump(tester, _bench, () async {
      calls++;
      return _bench.copyWith(weight: 20);
    });
    await tester.tap(find.text('Deload now'));
    await tester.pumpAndSettle();
    expect(find.text('Deload Dumbbell Bench Press?'), findsOneWidget);
    expect(find.textContaining('22.5 kg × 12 → 20 kg'), findsWidgets);
    expect(calls, 0);

    await tester.tap(find.widgetWithText(TextButton, 'Deload'));
    await tester.pumpAndSettle();
    expect(calls, 1);
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('Deload  20 kg × 12 → 17.5 kg'), findsOneWidget);
  });

  testWidgets('cancelling leaves the host and the row alone', (tester) async {
    var calls = 0;
    await _pump(tester, _bench, () async {
      calls++;
      return null;
    });
    await tester.tap(find.text('Deload now'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(calls, 0);
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('Deload  22.5 kg × 12 → 20 kg'), findsOneWidget);
  });

  testWidgets('a refused deload (null) keeps the shown state', (tester) async {
    var calls = 0;
    await _pump(tester, _bench, () async {
      calls++;
      return null;
    });
    await tester.tap(find.text('Deload now'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Deload'));
    await tester.pumpAndSettle();
    expect(calls, 1);
    expect(find.text('Deload  22.5 kg × 12 → 20 kg'), findsOneWidget);
  });

  testWidgets('at the floor the row is disabled and says why', (tester) async {
    await _pump(tester, _bench.copyWith(weight: 0), () async => null);
    expect(find.text('Deload  nothing lower to go to'), findsOneWidget);
    expect(_button(tester).onPressed, isNull);
  });
}
