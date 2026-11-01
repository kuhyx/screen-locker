// The warmup circle's fill is the app's one implicit animation: its duration
// is the motion token, and the OS "remove animations" setting zeroes it.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_tile.dart';

const _exercise = Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20);

Widget _tile({required bool disableAnimations}) => MediaQuery(
  data: MediaQueryData(disableAnimations: disableAnimations),
  child: MaterialApp(
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
      ),
    ),
  ),
);

Duration _warmupDuration(WidgetTester tester) => tester
    .widget<AnimatedContainer>(
      find.descendant(
        of: find.bySemanticsLabel('Squat warmup'),
        matching: find.byType(AnimatedContainer),
      ),
    )
    .duration;

void main() {
  testWidgets('the warmup circle animates on the base motion token', (
    tester,
  ) async {
    await tester.pumpWidget(_tile(disableAnimations: false));
    expect(_warmupDuration(tester), AppDuration.base);
  });

  testWidgets('with OS animations removed the warmup circle snaps', (
    tester,
  ) async {
    await tester.pumpWidget(_tile(disableAnimations: true));
    expect(_warmupDuration(tester), Duration.zero);
  });
}
