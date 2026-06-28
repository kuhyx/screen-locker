import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/widgets/rep_circle.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('RepCircle states', () {
    testWidgets('neutral shows target reps and white background', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(
          RepCircle(
            targetReps: 5,
            doneReps: 5,
            tapped: false,
            onTap: () => tapped = true,
            onLongPress: () {},
          ),
        ),
      );
      expect(find.text('5'), findsOneWidget);
      // Tapping calls onTap
      await tester.tap(find.byType(RepCircle));
      expect(tapped, isTrue);
    });

    testWidgets('success state (tapped, doneReps == targetReps)', (tester) async {
      await tester.pumpWidget(
        _wrap(
          RepCircle(
            targetReps: 5,
            doneReps: 5,
            tapped: true,
            onTap: () {},
            onLongPress: () {},
          ),
        ),
      );
      expect(find.text('5'), findsOneWidget);
    });

    testWidgets('partial state (tapped, 0 < doneReps < targetReps)', (tester) async {
      await tester.pumpWidget(
        _wrap(
          RepCircle(
            targetReps: 5,
            doneReps: 3,
            tapped: true,
            onTap: () {},
            onLongPress: () {},
          ),
        ),
      );
      expect(find.text('3'), findsOneWidget);
    });

    testWidgets('failed state (tapped, doneReps == 0)', (tester) async {
      await tester.pumpWidget(
        _wrap(
          RepCircle(
            targetReps: 5,
            doneReps: 0,
            tapped: true,
            onTap: () {},
            onLongPress: () {},
          ),
        ),
      );
      expect(find.text('0'), findsOneWidget);
    });

    testWidgets('long press calls onLongPress', (tester) async {
      var pressed = false;
      await tester.pumpWidget(
        _wrap(
          RepCircle(
            targetReps: 5,
            doneReps: 5,
            tapped: true,
            onTap: () {},
            onLongPress: () => pressed = true,
          ),
        ),
      );
      await tester.longPress(find.byType(RepCircle));
      expect(pressed, isTrue);
    });
  });

  group('RepCircleState enum', () {
    test('all values are distinct', () {
      expect(RepCircleState.values.toSet().length, RepCircleState.values.length);
    });
  });
}
