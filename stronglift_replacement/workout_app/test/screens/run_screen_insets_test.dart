// R7: the run screen fits one Pixel 6a screen with no scrolling, clear of the
// status bar and the gesture bar, in every phase.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fake_audio_platform.dart';
import '_run_screen_fixtures.dart';

const _dpr = 2.625;
const _physical = Size(1080, 2400);
const _topPx = 132.0;
const _bottomPx = 63.0;

void _pixel6a(WidgetTester tester) {
  tester.view
    ..physicalSize = _physical
    ..devicePixelRatio = _dpr
    ..padding = const FakeViewPadding(top: _topPx, bottom: _bottomPx);
  addTearDown(tester.view.reset);
}

/// Every scrollable has nowhere to scroll, nothing overflowed, and every
/// control sits between the status bar and the gesture bar.
void _expectFits(WidgetTester tester) {
  expect(tester.takeException(), isNull, reason: 'a layout overflow');
  for (final element in find.byType(Scrollable).evaluate()) {
    final position = Scrollable.of(element).position;
    expect(position.maxScrollExtent, 0);
  }
  final top = _topPx / _dpr;
  final bottom = (_physical.height - _bottomPx) / _dpr;
  for (final button in find.byType(IconButton).evaluate()) {
    final rect = tester.getRect(find.byWidget(button.widget));
    expect(rect.top, greaterThanOrEqualTo(top));
    expect(rect.bottom, lessThanOrEqualTo(bottom));
  }
  final slot = tester.getRect(find.byKey(const Key('run_map_slot')));
  expect(slot.top, greaterThanOrEqualTo(top));
}

void main() {
  setUp(installFakeAudioPlatform);

  testWidgets('idle, recording, paused and finished all fit', (tester) async {
    _pixel6a(tester);
    final h = RunHarness();
    await h.pump(tester);
    expect(find.byType(Scrollable), findsNothing);
    _expectFits(tester);

    // With the pace picker open: still nothing scrolls, nothing overflows.
    await tapKey(tester, 'run_pace_toggle');
    expect(find.byKey(const Key('run_pace_value')), findsOneWidget);
    expect(find.byType(Scrollable), findsNothing);
    _expectFits(tester);

    await tapKey(tester, 'run_start');
    await h.run(tester, 400);
    _expectFits(tester);

    await tapKey(tester, 'run_pause');
    _expectFits(tester);

    await tapKey(tester, 'run_finish');
    _expectFits(tester);
  });

  testWidgets('a long run (hours, tens of km) still fits at 2x text', (
    tester,
  ) async {
    _pixel6a(tester);
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearAllTestValues);
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_pace_toggle');
    _expectFits(tester);
    await tapKey(tester, 'run_start');
    await h.run(tester, 3000);
    // Three numbers in the row (distance, average pace, current pace).
    expect(find.byKey(const Key('run_pace_now')), findsOneWidget);
    _expectFits(tester);
  });
}
