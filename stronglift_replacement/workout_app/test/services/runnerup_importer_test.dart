@TestOn('vm')
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/runnerup_dav.dart';
import 'package:workout_app/services/runnerup_importer.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '_runnerup_fake_dufs.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late FakeDufs dufs;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    Sandbox.enabled = false;
    runnerUpImportStatus.value = RunnerUpImportStatus.idle;
    StorageService.resetForTesting();
    await StorageService.init();
    dufs = FakeDufs(fixtureTcx());
  });

  tearDown(() => Sandbox.enabled = false);

  test(
    'imports the PC history as display-only runs, then tells the PC',
    () async {
      final report = await makeImporter(dufs).runIfNeeded();

      expect(report.failures, isEmpty);
      expect(report.imported, 3);
      expect(dufs.depth, '1');
      final runs = await storedRuns();
      expect(runs, hasLength(3));
      for (final run in runs) {
        expect(run.track.source, RunSource.runnerupImport);
        expect(run.uploadState, RunUploadState.never);
      }
      // The walk is identified by its file name alone.
      expect(runs.map((r) => r.track.sport), contains(RunSport.walking));
      // The multi-lap RunnerUp file is summed like the PC sums it.
      final multi = runs.firstWhere((r) => r.tcxFilename.contains('08-12'));
      expect(multi.track.distanceM, greaterThan(0));
      expect(runnerUpImportStatus.value, RunnerUpImportStatus.done);

      expect(dufs.puts, ['PUT /RunnerUp/.workout_app_import.json']);
      final marker = jsonDecode(dufs.markers.single) as Map<String, dynamic>;
      expect(marker['completed_at'], '2026-11-10T08:00:00.000Z');
      final names = expectedMarkerNames(dufs.files);
      expect(names, isNotEmpty);
      expect(marker['count'], names.length);
      expect(marker['tcx_names'], names);
    },
  );

  test(
    'an app-made TCX that came back is still history, never pending',
    () async {
      final name = dufs.files.keys.firstWhere((n) => n.contains('17-30-00'));
      expect(
        decodeTcx(utf8.decode(dufs.files[name]!), fileName: name).source,
        RunSource.app,
        reason:
            'fixture must be an app-made file for this test to mean anything',
      );
      await makeImporter(dufs).runIfNeeded();
      final stored = (await storedRuns()).firstWhere(
        (r) => r.tcxFilename == name,
      );
      expect(stored.track.source, RunSource.runnerupImport);
      expect(stored.uploadState, RunUploadState.never);
    },
  );

  test(
    'twins are one run: stored once, listed once, app files not at all',
    () async {
      final original = dufs.files.keys.firstWhere((n) => n.contains('08-12'));
      final twin = original.replaceFirst('RunnerUp_', 'RunnerUp_Pixel_6a_');
      // Same <Id>, different bytes: the phone's own copy of the export.
      dufs.files[twin] = utf8Bytes('${utf8.decode(dufs.files[original]!)}\n');

      final report = await makeImporter(dufs).runIfNeeded();

      expect(report.failures, isEmpty);
      expect(report.duplicates, 1);
      expect(await storedRuns(), hasLength(3));
      final marker = jsonDecode(dufs.markers.single) as Map<String, dynamic>;
      final names = (marker['tcx_names'] as List<dynamic>).cast<String>();
      expect(names.where((n) => n.contains('08-12')), [original]);
      expect(marker['count'], names.length);
      expect(names.any((n) => n.contains('17-30-00')), isFalse);
    },
  );

  test('never PUTs a tcx anywhere; the only write is the dotfile', () async {
    await makeImporter(dufs).runIfNeeded();
    expect(dufs.puts, hasLength(1));
    expect(dufs.puts.single, startsWith('PUT /RunnerUp/.'));
    expect(dufs.puts.single, isNot(contains('.tcx')));
  });

  test('a rerun is a no-op once complete: no requests at all', () async {
    await makeImporter(dufs).runIfNeeded();
    final before = dufs.requests.length;

    final report = await makeImporter(dufs).runIfNeeded();

    expect(report.imported, 0);
    expect(dufs.requests, hasLength(before));
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.done);
    expect(await storedRuns(), hasLength(3));
  });

  test(
    'forgetting completion re-imports nothing new (dedupe by hash)',
    () async {
      await makeImporter(dufs).runIfNeeded();
      SharedPreferences.setMockInitialValues({});

      final report = await makeImporter(dufs).runIfNeeded();

      expect(report.imported, 0);
      expect(report.duplicates, 3);
      expect(await storedRuns(), hasLength(3));
    },
  );

  test('the marker path is a dotfile at the top of /RunnerUp', () {
    expect(kImportMarkerPath, '/RunnerUp/.workout_app_import.json');
    expect(kImportMarkerPath.split('/').last, startsWith('.'));
  });
}
