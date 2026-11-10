import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_uploader.dart';

import '../fake_audio_platform.dart';
import '../fake_run_service.dart';
import '../run_test_fixtures.dart';
import '_run_screen_fixtures.dart';

String _text(String id) =>
    (find.byKey(Key(id)).evaluate().single.widget as Text).data!;

void main() {
  setUp(installFakeAudioPlatform);

  group('problems are icons', () {
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
      mapBuilder: (context, points, _) => ValueListenableBuilder(
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
