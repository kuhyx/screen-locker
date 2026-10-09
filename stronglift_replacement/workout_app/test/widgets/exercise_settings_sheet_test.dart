import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';

final _base = ExerciseState.initial(workoutA.first);

Future<List<ExerciseState>> _pump(
  WidgetTester tester, [
  ExerciseState? state,
]) async {
  final edits = <ExerciseState>[];
  await tester.pumpWidget(
    MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: ExerciseSettingsSheet(
          state: state ?? _base,
          onChanged: edits.add,
          onDeload: () async => null,
        ),
      ),
    ),
  );
  return edits;
}

Future<void> _tapLabel(WidgetTester tester, String label) async {
  await tester.tap(find.bySemanticsLabel(label));
  await tester.pump();
}

void main() {
  testWidgets('switching mode reports it and keeps the sheet height', (
    tester,
  ) async {
    final edits = await _pump(tester);
    final before = tester.getSize(find.byType(ExerciseSettingsSheet));
    expect(find.textContaining('+2.5 kg per step'), findsOneWidget);

    await tester.tap(find.text('Reps'));
    await tester.pump();
    expect(edits.last.mode, ProgressionMode.reps);
    expect(find.textContaining('the weight never changes'), findsOneWidget);

    await tester.tap(find.text('Reps→kg'));
    await tester.pump();
    expect(edits.last.mode, ProgressionMode.doubleProgression);
    expect(find.textContaining('up to 12, then'), findsOneWidget);
    expect(tester.getSize(find.byType(ExerciseSettingsSheet)), before);
  });

  testWidgets('the rep range row only takes input in double mode', (
    tester,
  ) async {
    await _pump(tester);
    expect(find.bySemanticsLabel('Top reps up'), findsNothing);
    await tester.tap(find.text('Reps→kg'));
    await tester.pump();
    expect(find.bySemanticsLabel('Top reps up'), findsOneWidget);
  });

  testWidgets('n and m step and never cross', (tester) async {
    final edits = await _pump(
      tester,
      _base.copyWith(
        mode: ProgressionMode.doubleProgression,
        repsHigh: 7,
        repsLow: 6,
      ),
    );
    // m cannot reach n, n cannot drop to m.
    await _tapLabel(tester, 'Restart reps up');
    await _tapLabel(tester, 'Top reps down');
    expect(edits, isEmpty);

    await _tapLabel(tester, 'Top reps up');
    expect(edits.last.repsHigh, 8);
    await _tapLabel(tester, 'Restart reps up');
    expect(edits.last.repsLow, 7);
    await _tapLabel(tester, 'Restart reps down');
    expect(edits.last.repsLow, 6);
    await _tapLabel(tester, 'Top reps down');
    expect(edits.last.repsHigh, 7);
  });

  testWidgets('warmup switch and thresholds are reported', (tester) async {
    final edits = await _pump(tester);
    await tester.tap(find.text('Warmup set'));
    await tester.pump();
    expect(edits.last.hasWarmup, isFalse);

    await _tapLabel(tester, 'Wins needed down');
    expect(edits.last.successThreshold, 2);
    await _tapLabel(tester, 'Fails allowed up');
    expect(edits.last.failThreshold, 3);
    // Every edit carries the earlier ones, not just its own field.
    expect(edits.last.hasWarmup, isFalse);
  });

  testWidgets('rests step by 15 s as m:ss and stop at the bounds', (
    tester,
  ) async {
    final edits = await _pump(
      tester,
      _base.copyWith(restSuccessSecs: kMaxRestSecs, restFailSecs: kMinRestSecs),
    );
    expect(find.text('10:00'), findsOneWidget);
    expect(find.text('0:30'), findsOneWidget);
    // Already at the bounds: nothing to report.
    await _tapLabel(tester, 'Success rest up');
    await _tapLabel(tester, 'Fail rest down');
    expect(edits, isEmpty);

    await _tapLabel(tester, 'Success rest down');
    expect(edits.last.restSuccessSecs, kMaxRestSecs - kRestStepSecs);
    expect(find.text('9:45'), findsOneWidget);
    await _tapLabel(tester, 'Fail rest up');
    expect(edits.last.restFailSecs, kMinRestSecs + kRestStepSecs);
    await _tapLabel(tester, 'Warmup rest down');
    expect(edits.last.restWarmupSecs, kDefaultRestWarmupSecs - kRestStepSecs);
    // Every edit carries the earlier ones.
    expect(edits.last.restSuccessSecs, kMaxRestSecs - kRestStepSecs);
  });

  testWidgets('the warmup rest hides with the warmup, keeping the height', (
    tester,
  ) async {
    await _pump(tester);
    final before = tester.getSize(find.byType(ExerciseSettingsSheet));
    final warmupRest = find.bySemanticsLabel('Warmup rest up').hitTestable();
    expect(warmupRest, findsOneWidget);
    await tester.tap(find.text('Warmup set'));
    await tester.pump();
    expect(warmupRest, findsNothing);
    expect(tester.getSize(find.byType(ExerciseSettingsSheet)), before);
  });

  testWidgets('pause length steps from 14 and sets the end date', (
    tester,
  ) async {
    final edits = await _pump(tester);
    expect(find.text('$kDefaultPauseDays'), findsOneWidget);
    await _tapLabel(tester, 'Pause days up');
    await _tapLabel(tester, 'Pause days up');
    await _tapLabel(tester, 'Pause days down');
    await tester.tap(find.text('Pause'));
    await tester.pump();
    expect(
      edits.last.pausedUntil,
      pauseEnd(DateTime.now(), kDefaultPauseDays + 1),
    );
    expect(find.textContaining('Paused — back on'), findsOneWidget);

    await tester.tap(find.text('Resume'));
    await tester.pump();
    expect(edits.last.pausedUntil, isNull);
    expect(find.text('Pause'), findsOneWidget);
  });

  testWidgets('showExerciseSettingsSheet opens it as a bottom sheet', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showExerciseSettingsSheet(
              context,
              state: _base,
              onChanged: (_) {},
              onDeload: () async => null,
            ),
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(find.text(_base.name), findsOneWidget);
  });
}
