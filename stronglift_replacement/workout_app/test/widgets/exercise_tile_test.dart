import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

const _exercise = Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20.0);

final _state = ExerciseState.initial(_exercise);

ExerciseTile _tile({
  ExerciseState? state,
  List<bool>? tapped,
  List<int>? doneReps,
  bool warmupTapped = false,
  void Function(int)? onTapCircle,
  void Function(int)? onLongPressCircle,
  VoidCallback? onTapWarmup,
  ValueChanged<ExerciseState>? onSettingsChanged,
}) => ExerciseTile(
  exercise: _exercise,
  state: state ?? _state,
  tapped: tapped ?? [false, false, false],
  doneReps: doneReps ?? [5, 5, 5],
  warmupTapped: warmupTapped,
  onTapCircle: onTapCircle ?? (_) {},
  onLongPressCircle: onLongPressCircle ?? (_) {},
  onTapWarmup: onTapWarmup ?? () {},
  onSettingsChanged: onSettingsChanged ?? (_) {},
);

Color _cardColor(WidgetTester tester) =>
    tester.widget<Card>(find.byType(Card)).color!;

void main() {
  group('ExerciseTile', () {
    testWidgets('shows exercise name and weight info', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      expect(find.text('Squat'), findsOneWidget);
      expect(find.textContaining('3×5×20.0kg'), findsOneWidget);
    });

    testWidgets('warmup is the first circle, with its weight', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      expect(find.text('W×5'), findsOneWidget);
      expect(find.text('${_exercise.warmupWeight}'), findsOneWidget);
      final warmup = tester.getRect(find.bySemanticsLabel('Squat warmup'));
      final firstSet = tester.getRect(find.byType(RepCircle).first);
      expect(warmup.left, lessThan(firstSet.left));
      expect(warmup.height, firstSet.height);
    });

    testWidgets('calls onTapCircle when set circle tapped', (tester) async {
      var tappedIdx = -1;
      await tester.pumpWidget(_wrap(_tile(onTapCircle: (i) => tappedIdx = i)));
      await tester.tap(find.byType(RepCircle).first);
      expect(tappedIdx, 0);
    });

    testWidgets('calls onLongPressCircle on long press', (tester) async {
      var idx = -1;
      await tester.pumpWidget(_wrap(_tile(onLongPressCircle: (i) => idx = i)));
      await tester.longPress(find.byType(RepCircle).first);
      expect(idx, 0);
    });

    testWidgets('calls onTapWarmup once, then shows it done', (tester) async {
      var calls = 0;
      await tester.pumpWidget(_wrap(_tile(onTapWarmup: () => calls++)));
      await tester.tap(find.bySemanticsLabel('Squat warmup'));
      expect(calls, 1);

      await tester.pumpWidget(
        _wrap(_tile(warmupTapped: true, onTapWarmup: () => calls++)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('Squat warmup'));
      expect(calls, 1, reason: 'a done warmup is not tappable again');
    });

    testWidgets('warmup off keeps its slot: nothing moves', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      final setsWith = tester.getRect(find.byType(RepCircle).first);
      final tileWith = tester.getSize(find.byType(ExerciseTile));

      await tester.pumpWidget(
        _wrap(_tile(state: _state.copyWith(hasWarmup: false))),
      );
      expect(
        find.bySemanticsLabel('Squat warmup').hitTestable(),
        findsNothing,
      );
      expect(tester.getRect(find.byType(RepCircle).first), setsWith);
      expect(tester.getSize(find.byType(ExerciseTile)), tileWith);
    });

    testWidgets('card fill: green on success, red on a failed set', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(_tile()));
      final idle = _cardColor(tester);

      await tester.pumpWidget(
        _wrap(_tile(tapped: [true, true, true], doneReps: [5, 5, 5])),
      );
      final green = _cardColor(tester);
      expect(green, isNot(idle));

      await tester.pumpWidget(
        _wrap(_tile(tapped: [true, true, true], doneReps: [5, 5, 3])),
      );
      expect(_cardColor(tester), isNot(green));
      expect(_cardColor(tester), isNot(idle));
    });

    testWidgets('progress line shows streaks and the next step each way', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(_tile(state: _state.copyWith(successStreak: 2, failStreak: 1))),
      );
      expect(find.text('2/3 → 22.5 kg'), findsOneWidget);
      expect(find.text('1/2 → 17.5 kg'), findsOneWidget);

      await tester.pumpWidget(
        _wrap(_tile(state: _state.copyWith(mode: ProgressionMode.reps))),
      );
      expect(find.text('0/3 → 6 reps'), findsOneWidget);
      expect(find.text('0/2 → 4 reps'), findsOneWidget);
    });

    testWidgets('mode chip names the mode', (tester) async {
      await tester.pumpWidget(_wrap(_tile()));
      expect(find.text('kg'), findsOneWidget);
      await tester.pumpWidget(
        _wrap(_tile(state: _state.copyWith(mode: ProgressionMode.reps))),
      );
      expect(find.text('reps'), findsOneWidget);
      await tester.pumpWidget(
        _wrap(
          _tile(
            state: _state.copyWith(mode: ProgressionMode.doubleProgression),
          ),
        ),
      );
      expect(find.text('6→12'), findsOneWidget);
    });

    testWidgets('mode chip opens the sheet and reports edits', (tester) async {
      final edits = <ExerciseState>[];
      await tester.pumpWidget(_wrap(_tile(onSettingsChanged: edits.add)));
      await tester.tap(find.bySemanticsLabel('Squat progression settings'));
      await tester.pumpAndSettle();
      expect(find.byType(ExerciseSettingsSheet), findsOneWidget);
      await tester.tap(find.text('Reps'));
      await tester.pump();
      expect(edits.single.mode, ProgressionMode.reps);
    });

    testWidgets('paused: no circles, same height, never filled', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(_tile()));
      final size = tester.getSize(find.byType(ExerciseTile));
      final idle = _cardColor(tester);

      final until = pauseEnd(DateTime.now(), 14);
      await tester.pumpWidget(
        _wrap(
          _tile(
            state: _state.copyWith(pausedUntil: until),
            tapped: [true, true, true],
          ),
        ),
      );
      expect(find.byType(RepCircle), findsNothing);
      expect(find.bySemanticsLabel('Squat warmup'), findsNothing);
      expect(
        find.textContaining('back on ${formatShortDate(until)}'),
        findsOneWidget,
      );
      expect(tester.getSize(find.byType(ExerciseTile)), size);
      expect(_cardColor(tester), idle);
    });

    testWidgets('an expired pause shows the sets again', (tester) async {
      final past = DateTime.now().subtract(const Duration(days: 1));
      await tester.pumpWidget(
        _wrap(_tile(state: _state.copyWith(pausedUntil: past))),
      );
      expect(find.byType(RepCircle), findsNWidgets(3));
    });
  });
}
