// The pace picker: a pace icon, and when on, - m:ss + in 0:05 steps. No
// Scrollable, so it fits the no-scroll run screen.
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_pace_picker.dart';

Future<List<int>> _pump(
  WidgetTester tester, {
  required bool on,
  int seconds = 360,
}) async {
  final picked = <int>[];
  await tester.pumpWidget(
    MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) => RunPacePicker(
            on: on,
            seconds: seconds,
            onToggle: () => picked.add(-1),
            onChanged: (v) {
              picked.add(v);
              setState(() => seconds = v);
            },
          ),
        ),
      ),
    ),
  );
  return picked;
}

void main() {
  testWidgets('off: the icon only, and no scrollable', (tester) async {
    await _pump(tester, on: false);
    expect(find.byKey(const Key('run_pace_toggle')), findsOneWidget);
    expect(find.byKey(const Key('run_pace_value')), findsNothing);
    expect(find.byType(Scrollable), findsNothing);
  });

  testWidgets('the toggle reports a tap', (tester) async {
    final picked = await _pump(tester, on: false);
    await tester.tap(find.byKey(const Key('run_pace_toggle')));
    expect(picked, [-1]);
  });

  testWidgets('on: m:ss between minus and plus, 0:05 per tap', (tester) async {
    final picked = await _pump(tester, on: true);
    expect(find.text('6:00'), findsOneWidget);
    expect(find.byType(Scrollable), findsNothing);
    for (final id in ['run_pace_plus', 'run_pace_plus', 'run_pace_minus']) {
      await tester.tap(find.byKey(Key(id)));
      await tester.pump();
    }
    expect(picked, [365, 370, 365]);
  });

  testWidgets('holding a button repeats, and stops on release', (tester) async {
    final picked = await _pump(tester, on: true);
    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(const Key('run_pace_plus'))),
    );
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 10));
    for (var i = 0; i < 5; i++) {
      await tester.pump(kPaceRepeatEvery);
    }
    await gesture.up();
    await tester.pump();
    final steps = picked.length;
    expect(steps, greaterThan(3));
    await tester.pump(const Duration(seconds: 2));
    expect(picked, hasLength(steps));
    expect(picked, orderedEquals([...picked]..sort()));
  });

  testWidgets('a cancelled touch stops the repeat too', (tester) async {
    final picked = await _pump(tester, on: true);
    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(const Key('run_pace_minus'))),
    );
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 10));
    await gesture.cancel();
    final steps = picked.length;
    await tester.pump(const Duration(seconds: 2));
    expect(picked, hasLength(steps));
  });

  testWidgets('a hold stops by itself at the end of the range', (tester) async {
    final picked = await _pump(tester, on: true, seconds: 710);
    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(const Key('run_pace_plus'))),
    );
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 10));
    for (var i = 0; i < 20; i++) {
      await tester.pump(kPaceRepeatEvery);
    }
    await gesture.up();
    await tester.pump(const Duration(seconds: 1));
    expect(picked, [715, 720]);
    expect(find.text('12:00'), findsOneWidget);
  });

  testWidgets('clamps at 3:00 and 12:00', (tester) async {
    final low = await _pump(tester, on: true, seconds: kMinPaceTarget);
    await tester.tap(find.byKey(const Key('run_pace_minus')));
    expect(low, isEmpty);
    final high = await _pump(tester, on: true, seconds: kMaxPaceTarget);
    await tester.tap(find.byKey(const Key('run_pace_plus')));
    expect(high, isEmpty);
    expect(find.text('12:00'), findsOneWidget);
  });
}
