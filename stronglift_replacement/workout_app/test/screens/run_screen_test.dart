import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/widgets/run_map_slot.dart';

import '../fake_audio_platform.dart';
import '../fake_run_service.dart';
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
    expect(_text('run_pace'), '--:--');
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

  group('problems are icons', () {
    for (final (access, id, fixable) in [
      (LocationAccess.denied, 'run_issue_denied', false),
      (LocationAccess.deniedForever, 'run_issue_deniedForever', true),
      (LocationAccess.serviceOff, 'run_issue_serviceOff', true),
    ]) {
      testWidgets('${access.name}: red icon, start stays available', (
        tester,
      ) async {
        final h = RunHarness(access: access);
        await h.pump(tester);
        await tapKey(tester, 'run_start');

        expect(key(id), findsOneWidget);
        expect(find.byIcon(Icons.location_disabled), findsOneWidget);
        expect(key('run_start'), findsOneWidget);
        expect(h.service.calls, isEmpty);
        final button = tester.widget<IconButton>(key(id));
        expect(button.onPressed != null, fixable);
        if (fixable) {
          await tester.tap(key(id));
          expect(h.settingsOpened, [1]);
        }
      });
    }

    testWidgets('a mock fix shows the wrong-location icon', (tester) async {
      final h = RunHarness();
      await h.pump(tester);
      await tapKey(tester, 'run_start');
      h.source.controller.add(fixAt(0, 0, mocked: true));
      await tester.pumpAndSettle();
      expect(key('run_issue_mockedLocation'), findsOneWidget);
      expect(find.byIcon(Icons.wrong_location), findsOneWidget);
    });

    testWidgets('a location stream error shows the gps-off icon', (
      tester,
    ) async {
      final h = RunHarness();
      await h.pump(tester);
      await tapKey(tester, 'run_start');
      h.source.controller.addError(StateError('gps off'));
      await tester.pumpAndSettle();
      expect(key('run_issue_streamError'), findsOneWidget);
      expect(find.byIcon(Icons.gps_off), findsOneWidget);
    });

    testWidgets('a run with no fixes says so and saves nothing', (
      tester,
    ) async {
      final h = RunHarness();
      await h.pump(tester);
      await tapKey(tester, 'run_start');
      await tapKey(tester, 'run_finish');
      expect(key('run_issue_tooShort'), findsOneWidget);
      expect(h.saved, isEmpty);
      expect(key('run_saved_ok'), findsNothing);
    });

    testWidgets('denied notifications and a dead service are flagged', (
      tester,
    ) async {
      final hidden = RunHarness(
        service: FakeForegroundRunClient(
          permissionGranted: false,
          grantOnRequest: false,
        ),
      );
      await hidden.pump(tester);
      await tapKey(tester, 'run_start');
      expect(key('run_service_issue'), findsOneWidget);
      expect(find.byIcon(Icons.notifications_off), findsOneWidget);

      final dead = RunHarness(
        service: FakeForegroundRunClient(startSucceeds: false),
      );
      await dead.pump(tester);
      await tapKey(tester, 'run_start');
      expect(find.byIcon(Icons.warning_amber), findsOneWidget);
    });

    testWidgets('a save that throws shows the failed icon', (tester) async {
      final h = RunHarness(saveThrows: true);
      await h.pump(tester);
      await tapKey(tester, 'run_start');
      await h.run(tester, 4);
      await tapKey(tester, 'run_finish');
      await tester.pumpAndSettle();
      expect(key('run_saved_failed'), findsOneWidget);
      expect(key('run_saved_ok'), findsNothing);
    });
  });

  testWidgets('the upload badge follows the queue and retries on tap', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    final cases = {
      UploadHealth.idle: Icons.cloud_done,
      UploadHealth.uploading: Icons.cloud_upload,
      UploadHealth.retrying: Icons.cloud_off,
      UploadHealth.notConfigured: Icons.link_off,
      UploadHealth.sandbox: Icons.cloud_queue,
    };
    for (final entry in cases.entries) {
      h.uploader.state.value = RunUploadStatus(entry.key, 2);
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: key('run_upload_badge'),
          matching: find.byIcon(entry.value),
        ),
        findsOneWidget,
        reason: entry.key.name,
      );
      expect(_text('run_upload_pending'), '2');
    }
    h.uploader.state.value = const RunUploadStatus(UploadHealth.idle, 0);
    await tester.pumpAndSettle();
    expect(key('run_upload_pending'), findsNothing);

    final before = h.uploader.passes;
    await tapKey(tester, 'run_upload_badge');
    expect(h.uploader.passes, before + 1);
  });

  testWidgets('a map builder replaces the placeholder and gets the points', (
    tester,
  ) async {
    final h = RunHarness();
    List<RunPoint>? seen;
    await h.pump(
      tester,
      mapBuilder: (context, points) => ValueListenableBuilder(
        valueListenable: points,
        builder: (context, list, _) {
          seen = list;
          return Text('${list.length}', key: const Key('custom_map'));
        },
      ),
    );
    expect(key('run_map_slot'), findsNothing);
    await tapKey(tester, 'run_start');
    await h.run(tester, 5);
    expect(_text('custom_map'), '5');
    expect(seen, hasLength(5));
  });
}
