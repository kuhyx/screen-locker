import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/break_banner.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

void main() {
  group('BreakBanner', () {
    testWidgets('displays label and formatted time', (tester) async {
      await tester.pumpWidget(
        _wrap(
          BreakBanner(
            breakRemaining: 90,
            breakLabel: 'Rest',
            onSkip: () {},
          ),
        ),
      );
      expect(find.text('Rest'), findsOneWidget);
      expect(find.text('01:30'), findsOneWidget);
    });

    testWidgets('formats time below one minute correctly', (tester) async {
      await tester.pumpWidget(
        _wrap(
          BreakBanner(
            breakRemaining: 5,
            breakLabel: 'Warmup rest',
            onSkip: () {},
          ),
        ),
      );
      expect(find.text('00:05'), findsOneWidget);
    });

    testWidgets('skip button calls onSkip', (tester) async {
      var skipped = false;
      await tester.pumpWidget(
        _wrap(
          BreakBanner(
            breakRemaining: 60,
            breakLabel: 'Rest',
            onSkip: () => skipped = true,
          ),
        ),
      );
      await tester.tap(find.text('Skip'));
      expect(skipped, isTrue);
    });

    testWidgets('zero seconds formats as 00:00', (tester) async {
      await tester.pumpWidget(
        _wrap(
          BreakBanner(
            breakRemaining: 0,
            breakLabel: 'Rest',
            onSkip: () {},
          ),
        ),
      );
      expect(find.text('00:00'), findsOneWidget);
    });
  });
}
