import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/break_banner.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

BreakBanner _banner({
  bool active = true,
  int breakRemaining = 90,
  VoidCallback? onSkip,
  bool finished = false,
  bool canFinish = false,
  VoidCallback? onReset,
  VoidCallback? onFinish,
}) => BreakBanner(
  active: active,
  breakRemaining: breakRemaining,
  onSkip: onSkip ?? () {},
  finished: finished,
  canFinish: canFinish,
  onReset: onReset ?? () {},
  onFinish: onFinish ?? () {},
);

Visibility _slotOf(WidgetTester tester, String text) =>
    tester.widget<Visibility>(
      find.ancestor(of: find.text(text), matching: find.byType(Visibility)),
    );

void main() {
  group('BreakBanner', () {
    testWidgets('shows only the formatted time — no label', (tester) async {
      await tester.pumpWidget(_wrap(_banner()));
      expect(find.text('01:30'), findsOneWidget);
      expect(find.textContaining('Rest'), findsNothing);
    });

    testWidgets('formats time below one minute correctly', (tester) async {
      await tester.pumpWidget(_wrap(_banner(breakRemaining: 5)));
      expect(find.text('00:05'), findsOneWidget);
    });

    testWidgets('skip button calls onSkip', (tester) async {
      var skipped = false;
      await tester.pumpWidget(_wrap(_banner(onSkip: () => skipped = true)));
      await tester.tap(find.text('Skip'));
      expect(skipped, isTrue);
    });

    testWidgets('keeps its height and hides Skip while idle', (tester) async {
      await tester.pumpWidget(_wrap(_banner(active: false, breakRemaining: 0)));
      expect(
        tester.getSize(find.byType(BreakBanner)).height,
        BreakBanner.height,
      );
      expect(find.text('00:00'), findsOneWidget);
      // Skip keeps its space (nothing may move when a rest starts) but is
      // neither visible nor tappable.
      final skip = _slotOf(tester, 'Skip');
      expect(skip.visible, isFalse);
      expect(skip.maintainSize, isTrue);
    });

    testWidgets('Reset calls onReset', (tester) async {
      var reset = false;
      await tester.pumpWidget(_wrap(_banner(onReset: () => reset = true)));
      await tester.tap(find.text('Reset'));
      expect(reset, isTrue);
    });

    testWidgets('Finish is disabled until every set is done', (tester) async {
      var finished = 0;
      await tester.pumpWidget(_wrap(_banner(onFinish: () => finished++)));
      await tester.tap(find.text('Finish'));
      expect(finished, 0);

      await tester.pumpWidget(
        _wrap(_banner(canFinish: true, onFinish: () => finished++)),
      );
      await tester.tap(find.text('Finish'));
      expect(finished, 1);
    });

    testWidgets('a finished workout hides Reset and Finish, space kept', (
      tester,
    ) async {
      await tester.pumpWidget(_wrap(_banner()));
      final finishAt = tester.getRect(find.text('Finish'));
      await tester.pumpWidget(_wrap(_banner(finished: true)));
      for (final label in ['Reset', 'Finish']) {
        final slot = _slotOf(tester, label);
        expect(slot.visible, isFalse, reason: label);
        expect(slot.maintainSize, isTrue, reason: label);
      }
      expect(tester.getRect(find.text('Finish')), finishAt);
    });
  });
}
