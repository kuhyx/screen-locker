import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/animated_counter.dart';

Widget _host(int value, {bool disableAnimations = false}) => MediaQuery(
  data: MediaQueryData(disableAnimations: disableAnimations),
  child: Directionality(
    textDirection: TextDirection.ltr,
    child: AnimatedCounter(value: value, builder: (n) => Text('n=$n')),
  ),
);

void main() {
  testWidgets('counts up from zero to the real value on arrival', (
    tester,
  ) async {
    await tester.pumpWidget(_host(3));
    expect(find.text('n=0'), findsOneWidget);

    await tester.pump(AppDuration.slow ~/ 2);
    final mid = find.textContaining('n=');
    expect(mid, findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.text('n=3'), findsOneWidget);
  });

  testWidgets('animates from the shown number to a new one, not from zero', (
    tester,
  ) async {
    await tester.pumpWidget(_host(2));
    await tester.pumpAndSettle();
    await tester.pumpWidget(_host(5));
    await tester.pump(const Duration(milliseconds: 1));
    final shown = int.parse(
      (tester.widget<Text>(find.textContaining('n=')).data!).substring(2),
    );
    expect(shown, inInclusiveRange(2, 3));
    await tester.pumpAndSettle();
    expect(find.text('n=5'), findsOneWidget);
  });

  testWidgets('a zero value has nothing to animate', (tester) async {
    await tester.pumpWidget(_host(0));
    expect(find.text('n=0'), findsOneWidget);
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('with OS animations off the true value shows at once', (
    tester,
  ) async {
    await tester.pumpWidget(_host(4, disableAnimations: true));
    await tester.pump();
    expect(find.text('n=4'), findsOneWidget);
  });
}
