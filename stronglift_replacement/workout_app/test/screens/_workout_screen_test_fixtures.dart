// Shared fixtures for the workout-screen test files.
//
// The three pump/gesture helpers were locals inside `main()`. They all wrap
// the interaction in `runAsync`: the widget-test zone fakes async, so a
// sqflite-ffi write started from a plain pump hangs and takes the isolate
// down on shutdown.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/ui/theme.dart';

Map<String, dynamic> completeSaved() => {
  'workoutType': 'A',
  'startTimeMs': DateTime.now().millisecondsSinceEpoch,
  'tapped': [
    [true, true, true],
    [true, true, true],
  ],
  'doneReps': [
    [5, 5, 5],
    [5, 5, 5],
  ],
  'warmupTapped': [false, false],
};

const testExercises = [
  Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20.0),
  Exercise(name: 'Press', sets: 3, reps: 5, weight: 15.0),
];

Widget wrapWorkout({
  String type = 'A',
  List<Exercise> exercises = testExercises,
  Map<String, dynamic>? savedState,
}) => MaterialApp(
  theme: buildAppTheme(),
  home: WorkoutScreen(
    workoutType: type,
    exercises: exercises,
    savedState: savedState,
  ),
);

Future<void> pumpWorkout(WidgetTester tester, Widget w) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(w);
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await tester.pump();
}

Future<void> tapReal(WidgetTester tester, Finder f) async {
  await tester.runAsync(() async {
    await tester.tap(f);
    await Future<void>.delayed(const Duration(milliseconds: 100));
  });
  await tester.pump();
}

// tester.longPress() does internal fake-clock pumps that conflict with
// runAsync, so drive a manual gesture whose hold exceeds the long-press
// timeout on the real clock (keeping the resulting DB write on the real loop).
Future<void> longPressReal(WidgetTester tester, Finder f) async {
  final center = tester.getCenter(f);
  await tester.runAsync(() async {
    final gesture = await tester.startGesture(center);
    await Future<void>.delayed(const Duration(milliseconds: 700));
    await gesture.up();
    await Future<void>.delayed(const Duration(milliseconds: 100));
  });
  await tester.pump();
}
