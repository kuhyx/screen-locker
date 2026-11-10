// Before a run the map shows and follows where the user is; those display-only
// fixes never reach the recorded track.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/widgets/run_map.dart';

import '../fake_audio_platform.dart';
import '../run_test_fixtures.dart';
import '_run_screen_fixtures.dart';

MapCamera _camera(WidgetTester tester) =>
    MapCamera.of(tester.element(find.byType(RichAttributionWidget)));

Future<void> _idleFix(
  WidgetTester tester,
  RunHarness h,
  int second,
  double northM,
) async {
  h.source.controller.add(fixAt(second, northM));
  await tester.pump();
  await tester.pump();
}

void main() {
  setUp(installFakeAudioPlatform);

  testWidgets('opening the screen asks for location and shows the map', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    expect(h.source.requests, 1);
    expect(find.byType(RunMap), findsOneWidget);
    expect(key('run_start'), findsOneWidget);
  });

  testWidgets('the idle map is centred on the current fix, with a marker', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    // Zoomed-out Poland until the first fix arrives.
    expect(_camera(tester).zoom, lessThan(8));

    await _idleFix(tester, h, 0, 0);
    final fix = fixAt(0, 0);
    final camera = _camera(tester);
    expect(camera.center.latitude, closeTo(fix.latitude, 1e-6));
    expect(camera.center.longitude, closeTo(fix.longitude, 1e-6));
    expect(camera.zoom, greaterThan(15));
    expect(
      tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers,
      hasLength(1),
    );
    expect(find.byType(PolylineLayer), findsNothing);

    await _idleFix(tester, h, 2, 40);
    expect(
      _camera(tester).center.latitude,
      closeTo(fixAt(2, 40).latitude, 1e-6),
    );
  });

  testWidgets('recentre jumps to the latest fix with zero run points', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await _idleFix(tester, h, 0, 0);

    await tester.drag(find.byType(FlutterMap), const Offset(150, 0));
    await tester.pump();
    final dragged = _camera(tester).center.longitude;
    expect(find.byIcon(Icons.my_location), findsOneWidget);

    // A newer fix does not drag the camera while the user is looking around.
    await _idleFix(tester, h, 2, 40);
    expect(_camera(tester).center.longitude, closeTo(dragged, 1e-9));

    await tester.tap(find.byIcon(Icons.my_location));
    await tester.pump();
    final center = _camera(tester).center;
    expect(center.latitude, closeTo(fixAt(2, 40).latitude, 1e-6));
    expect(center.longitude, closeTo(fixAt(2, 40).longitude, 1e-6));
    expect(find.byIcon(Icons.my_location), findsNothing);
  });

  testWidgets('idle fixes are never recorded into the track', (tester) async {
    final h = RunHarness();
    await h.pump(tester);
    for (var i = 0; i < 4; i++) {
      await _idleFix(tester, h, i * 2, i * 6.0);
    }
    await tapKey(tester, 'run_start');
    expect(find.byType(PolylineLayer), findsNothing);
    await h.run(tester, 5, from: 10);
    await tapKey(tester, 'run_finish');
    expect(h.saved.single.points, hasLength(5));
  });
}
