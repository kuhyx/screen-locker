// In the sandbox flavor the idle map sits on the replay's first fix: one dot
// at the loop's start, not the whole lap walked before the run.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_audio_platform.dart';
import '../fake_run_uploader.dart';
import '_run_screen_fixtures.dart';

MapCamera _camera(WidgetTester tester) =>
    MapCamera.of(tester.element(find.byType(RichAttributionWidget)));

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    installFakeAudioPlatform();
    Sandbox.enabled = true;
    // Fast enough that a walking replay would show within the test.
    Sandbox.runReplayFactor = 1000000;
  });

  tearDown(() {
    Sandbox.enabled = false;
    Sandbox.runReplayFactor = Sandbox.defaultReplayFactor;
  });

  testWidgets('idle, the map sits on the replay first fix and stays there', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: RunScreen(uploader: FakeRunUploader(), mapBuilder: fakeTileMap),
      ),
    );
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pump();
    await tester.pump();

    final first = sandboxLoopFixes(DateTime.now()).first;
    expect(_camera(tester).center.latitude, closeTo(first.latitude, 1e-6));
    expect(_camera(tester).center.longitude, closeTo(first.longitude, 1e-6));
    expect(find.byKey(const Key('run_start')), findsOneWidget);

    // Not walking the lap before the run: a single dot, no route.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();
    expect(find.byType(PolylineLayer), findsNothing);
    expect(_camera(tester).center.latitude, closeTo(first.latitude, 1e-6));
  });
}
