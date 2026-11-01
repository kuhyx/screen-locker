import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';

Future<Duration> _resolved(
  WidgetTester tester, {
  required bool disableAnimations,
  Duration wanted = AppDuration.base,
}) async {
  late Duration out;
  await tester.pumpWidget(
    MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: Builder(
        builder: (context) {
          out = motionDuration(context, wanted);
          return const SizedBox();
        },
      ),
    ),
  );
  return out;
}

void main() {
  test('the duration scale is the frozen four-step one', () {
    expect(AppDuration.instant, Duration.zero);
    expect(AppDuration.fast, const Duration(milliseconds: 120));
    expect(AppDuration.base, const Duration(milliseconds: 200));
    expect(AppDuration.slow, const Duration(milliseconds: 320));
  });

  test('the easing curves are the frozen cubic-beziers', () {
    expect(AppCurve.standard, const Cubic(0.2, 0, 0, 1));
    expect(AppCurve.decelerate, const Cubic(0, 0, 0, 1));
    expect(AppCurve.accelerate, const Cubic(0.3, 0, 1, 1));
  });

  testWidgets('motionDuration keeps the token when animations are on', (
    tester,
  ) async {
    expect(await _resolved(tester, disableAnimations: false), AppDuration.base);
  });

  testWidgets('motionDuration collapses to zero when the OS removes motion', (
    tester,
  ) async {
    expect(
      await _resolved(
        tester,
        disableAnimations: true,
        wanted: AppDuration.slow,
      ),
      Duration.zero,
    );
  });
}
