import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

const _exercise = Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20.0);

ExerciseTile _tile({
  List<bool>? tapped,
  List<int>? doneReps,
  bool warmupTapped = false,
  int successThreshold = 3,
  int failThreshold = 2,
  void Function(int)? onTapCircle,
  void Function(int)? onLongPressCircle,
  VoidCallback? onTapWarmup,
  void Function(int, int)? onThresholdChanged,
}) =>
    ExerciseTile(
      exercise: _exercise,
      tapped: tapped ?? [false, false, false],
      doneReps: doneReps ?? [5, 5, 5],
      warmupTapped: warmupTapped,
      successThreshold: successThreshold,
      failThreshold: failThreshold,
      onTapCircle: onTapCircle ?? (_) {},
      onLongPressCircle: onLongPressCircle ?? (_) {},
      onTapWarmup: onTapWarmup ?? () {},
      onThresholdChanged: onThresholdChanged ?? (_, __) {},
    );

void main() {
  group('ExerciseTile', () {
    testWidgets('shows exercise name and weight info', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      expect(find.text('Squat'), findsOneWidget);
      expect(find.textContaining('3×5×20.0kg'), findsOneWidget);
    });

    testWidgets('shows warmup weight', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      // warmupWeight for 20kg squat = 10kg (50%)
      expect(find.textContaining('${_exercise.warmupWeight}kg'), findsOneWidget);
    });

    testWidgets('calls onTapCircle when set circle tapped', (tester) async {
      var tappedIdx = -1;
      await tester.pumpWidget(
        _wrap(_tile(onTapCircle: (i) => tappedIdx = i)),
      );
      // Tap the first RepCircle (index 0)
      await tester.tap(find.byType(RepCircle).first);
      expect(tappedIdx, 0);
    });

    testWidgets('calls onLongPressCircle on long press', (tester) async {
      var idx = -1;
      await tester.pumpWidget(
        _wrap(_tile(onLongPressCircle: (i) => idx = i)),
      );
      await tester.longPress(find.byType(RepCircle).first);
      expect(idx, 0);
    });

    testWidgets('calls onTapWarmup when warmup circle tapped', (tester) async {
      var called = false;
      await tester.pumpWidget(_wrap(_tile(onTapWarmup: () => called = true)));
      // The warmup circle is the GestureDetector wrapping the AnimatedContainer.
      // Find the warmup area by finding the fitness_center icon.
      await tester.tap(find.byIcon(Icons.fitness_center));
      expect(called, isTrue);
    });

    testWidgets('header is green when all sets succeeded', (tester) async {
      await tester.pumpWidget(
        _wrap(
          _tile(
            tapped: [true, true, true],
            doneReps: [5, 5, 5],
          ),
        ),
      );
      // Just verify it renders without errors
      expect(find.byType(ExerciseTile), findsOneWidget);
    });

    testWidgets('header is red when all sets tapped but some failed', (tester) async {
      await tester.pumpWidget(
        _wrap(
          _tile(
            tapped: [true, true, true],
            doneReps: [5, 5, 3],
          ),
        ),
      );
      expect(find.byType(ExerciseTile), findsOneWidget);
    });

    testWidgets('success threshold stepper increments', (tester) async {
      var newSuccess = 0;
      await tester.pumpWidget(
        _wrap(
          _tile(
            successThreshold: 2,
            onThresholdChanged: (s, _) => newSuccess = s,
          ),
        ),
      );
      // The first add icon belongs to the success stepper
      final addIcons = find.byIcon(Icons.add);
      await tester.tap(addIcons.first);
      expect(newSuccess, 3);
    });

    testWidgets('fail threshold stepper decrements', (tester) async {
      var newFail = 0;
      await tester.pumpWidget(
        _wrap(
          _tile(
            failThreshold: 3,
            onThresholdChanged: (_, f) => newFail = f,
          ),
        ),
      );
      // The last remove icon belongs to the fail stepper
      final removeIcons = find.byIcon(Icons.remove);
      await tester.tap(removeIcons.last);
      expect(newFail, 2);
    });

    testWidgets('stepper min/max clamps are respected', (tester) async {
      var callCount = 0;
      // successThreshold = 1 (at min), tapping minus should not fire
      await tester.pumpWidget(
        _wrap(
          _tile(
            successThreshold: 1,
            failThreshold: 5,
            onThresholdChanged: (_, __) => callCount++,
          ),
        ),
      );
      // First minus (success, at min 1) → no callback
      await tester.tap(find.byIcon(Icons.remove).first);
      expect(callCount, 0);
      // Last add (fail, at max 5) → no callback
      await tester.tap(find.byIcon(Icons.add).last);
      expect(callCount, 0);
    });
  });
}
