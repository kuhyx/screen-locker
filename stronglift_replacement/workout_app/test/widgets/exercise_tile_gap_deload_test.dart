import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_tile.dart';

const _exercise = Exercise(name: 'Squat', sets: 3, reps: 5, weight: 17.5);

Widget _tile(ProgressionTarget? from) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(
    body: ExerciseTile(
      exercise: _exercise,
      state: ExerciseState.initial(_exercise),
      tapped: const [false, false, false],
      doneReps: const [5, 5, 5],
      warmupTapped: false,
      onTapCircle: (_) {},
      onLongPressCircle: (_) {},
      onTapWarmup: () {},
      onSettingsChanged: (_) {},
      onDeload: () async => null,
      deloadedFrom: from,
    ),
  ),
);

TextDecoration? _decoration(WidgetTester tester, String text) =>
    tester.widget<Text>(find.text(text)).style?.decoration;

void main() {
  testWidgets('a gap deload shows the old weight struck through + arrow', (
    tester,
  ) async {
    await tester.pumpWidget(_tile(const ProgressionTarget(20, 5)));
    expect(find.byIcon(Icons.arrow_downward), findsOneWidget);
    expect(_decoration(tester, '20.0kg'), TextDecoration.lineThrough);
    expect(find.textContaining('3×5×17.5kg'), findsOneWidget);
    expect(find.bySemanticsLabel('Squat deloaded after a break'), findsOne);
  });

  testWidgets('a reps-only cut strikes the old reps', (tester) async {
    await tester.pumpWidget(_tile(const ProgressionTarget(17.5, 7)));
    expect(_decoration(tester, '×7'), TextDecoration.lineThrough);
  });

  testWidgets('no deload, or one already undone: no arrow', (tester) async {
    await tester.pumpWidget(_tile(null));
    expect(find.byIcon(Icons.arrow_downward), findsNothing);
    await tester.pumpWidget(_tile(const ProgressionTarget(17.5, 5)));
    expect(find.byIcon(Icons.arrow_downward), findsNothing);
  });
}
