import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/widgets/run_map_slot.dart';

import '../fake_audio_platform.dart';
import '../run_test_fixtures.dart';
import '_run_screen_fixtures.dart';

String _text(String id) =>
    (find.byKey(Key(id)).evaluate().single.widget as Text).data!;

bool _enabled(WidgetTester tester, String id) =>
    tester.widget<IconButton>(key(id)).onPressed != null;

class _GatedSource extends ManualPositionSource {
  final gate = Completer<void>();

  @override
  Future<LocationAccess> requestAccess() async {
    await gate.future;
    return LocationAccess.granted;
  }
}

void main() {
  setUp(installFakeAudioPlatform);

  testWidgets('idle: sport toggle, start, zeros and the map slot', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);

    expect(key('run_start'), findsOneWidget);
    expect(key('run_sport'), findsOneWidget);
    expect(key('run_pause'), findsNothing);
    expect(key('run_map_slot'), findsOneWidget);
    expect(find.byType(RunMapSlot), findsOneWidget);
    expect(_text('run_time'), '0:00');
    expect(_text('run_distance'), '0.00');
    expect(_text('run_pace'), '-:--');
    expect(key('run_upload_badge'), findsOneWidget);
    expect(h.uploader.passes, 1);
  });

  testWidgets('the sport can be switched until the run starts', (tester) async {
    final h = RunHarness();
    await h.pump(tester);

    await tester.tap(find.byIcon(Icons.directions_walk));
    await tester.pumpAndSettle();
    expect(
      find.descendant(
        of: key('run_sport'),
        matching: find.byIcon(Icons.directions_walk),
      ),
      findsOneWidget,
    );

    await tapKey(tester, 'run_start');
    expect(find.byIcon(Icons.directions_walk), findsOneWidget);
    expect(key('run_sport'), findsNothing);
    expect(h.service.starts, [true]);
  });

  testWidgets('a run shows live numbers and can pause, resume, finish', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');

    expect(key('run_start'), findsNothing);
    expect(key('run_pause'), findsOneWidget);
    await h.run(tester, 8);
    expect(_text('run_time'), '0:14');
    expect(_text('run_distance'), '0.04');
    expect(_text('run_pace'), '5:33');

    await tapKey(tester, 'run_pause');
    expect(key('run_resume'), findsOneWidget);
    expect(key('run_pause'), findsNothing);
    await h.run(tester, 3, from: 8);
    expect(_text('run_time'), '0:14');

    await tapKey(tester, 'run_resume');
    expect(key('run_pause'), findsOneWidget);

    await tapKey(tester, 'run_finish');
    await tester.pumpAndSettle();
    expect(key('run_saved_ok'), findsOneWidget);
    expect(h.saved.single.points, hasLength(8));
    expect(h.cues.finishes, 1);
    expect(h.service.calls.last, 'stop');
    expect(key('run_again'), findsOneWidget);
    expect(key('run_close'), findsOneWidget);
    expect(key('run_finish'), findsNothing);
  });

  testWidgets('finishing from pause works too', (tester) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    await h.run(tester, 4);
    await tapKey(tester, 'run_pause');
    await tapKey(tester, 'run_finish');
    expect(key('run_saved_ok'), findsOneWidget);
  });

  testWidgets('"again" starts a fresh recording, "close" leaves', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    await h.run(tester, 4);
    await tapKey(tester, 'run_finish');

    await tapKey(tester, 'run_again');
    expect(key('run_start'), findsOneWidget);
    expect(_text('run_distance'), '0.00');
    expect(key('run_saved_ok'), findsNothing);

    await tapKey(tester, 'run_start');
    await tapKey(tester, 'run_finish');
    await tester.pumpAndSettle();
    await tapKey(tester, 'run_close');
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsNothing);
  });

  testWidgets('back does nothing while recording, works before and after', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    await h.run(tester, 4);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsOneWidget);

    await tapKey(tester, 'run_pause');
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsOneWidget);

    await tapKey(tester, 'run_finish');
    await tester.pumpAndSettle();
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsNothing);
  });

  testWidgets('start is disabled while the permission prompt is open', (
    tester,
  ) async {
    final source = _GatedSource();
    final h = RunHarness(source: source);
    await h.pump(tester);
    expect(_enabled(tester, 'run_start'), isTrue);

    await tester.tap(key('run_start'));
    await tester.pumpAndSettle();
    expect(_enabled(tester, 'run_start'), isFalse);

    source.gate.complete();
    await tester.pumpAndSettle();
    expect(key('run_pause'), findsOneWidget);
  });

  testWidgets('while the run is being saved a spinner shows and exits wait', (
    tester,
  ) async {
    final gate = Completer<void>();
    final h = RunHarness(saveGate: gate);
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    await h.run(tester, 4);

    await tester.tap(key('run_finish'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
    expect(key('run_saving'), findsOneWidget);
    expect(_enabled(tester, 'run_again'), isFalse);
    expect(_enabled(tester, 'run_close'), isFalse);

    gate.complete();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pumpAndSettle();
    expect(key('run_saving'), findsNothing);
    expect(key('run_saved_ok'), findsOneWidget);
    expect(_enabled(tester, 'run_again'), isTrue);
  });
}
