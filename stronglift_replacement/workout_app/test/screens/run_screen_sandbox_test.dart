// A whole run in the sandbox flavor, end to end with the real wiring: the
// replayed GPS loop, the recorder, the database and the no-op uploader.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_audio_platform.dart';
import '../fake_run_uploader.dart';
import '_run_screen_fixtures.dart';

void main() {
  late Directory backupDir;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeAudioPlatform();
    backupDir = Directory.systemTemp.createTempSync('run_sandbox_backup_');
    BackupService.baseDir = backupDir.path;
    Sandbox.enabled = true;
    // 2 s of track per 2 microseconds: the lap replays in about a second.
    Sandbox.runReplayFactor = 1000000;
  });

  tearDown(() async {
    Sandbox.enabled = false;
    Sandbox.runReplayFactor = Sandbox.defaultReplayFactor;
    // insertRun fires an unawaited backup; let it land before the dir goes.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    BackupService.baseDir = '/sdcard/WorkoutTracker';
    backupDir.deleteSync(recursive: true);
  });

  testWidgets('a replayed lap is recorded, saved pending, never uploaded', (
    tester,
  ) async {
    final uploader = FakeRunUploader();
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: RunScreen(uploader: uploader),
      ),
    );

    List<RunRecord>? runs;
    await tester.runAsync(() async {
      await tester.tap(key('run_start'));
      final deadline = DateTime.now().add(const Duration(seconds: 40));
      // The lap is done when the distance stops growing near 4 km.
      var last = -1.0;
      while (DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 200));
        await tester.pump();
        final shown = double.parse(
          (find.byKey(const Key('run_distance')).evaluate().single.widget
                  as Text)
              .data!,
        );
        if (shown >= 3.99 && shown == last) break;
        last = shown;
      }
      await tester.tap(key('run_finish'));
      await Future<void>.delayed(const Duration(milliseconds: 500));
      runs = await StorageService.instance.listRuns();
    });
    await tester.pump();

    expect(key('run_saved_ok'), findsOneWidget);
    final run = runs!.single;
    expect(run.track.sport, RunSport.running);
    expect(run.track.source, RunSource.app);
    expect(run.track.distanceM, closeTo(4000, 20));
    expect(run.uploadState, RunUploadState.pending);
    expect(run.tcxFilename, endsWith('_Running.tcx'));
  });
}
