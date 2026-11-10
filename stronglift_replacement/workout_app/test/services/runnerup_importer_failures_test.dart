@TestOn('vm')
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/runnerup_importer.dart';
import 'package:workout_app/services/storage_service.dart';

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
    '401 leaves it incomplete and failed, then a fix completes it',
    () async {
      dufs.listStatus = 401;
      final report = await makeImporter(dufs).runIfNeeded();

      expect(report.failures.single, contains('401'));
      expect(runnerUpImportStatus.value, RunnerUpImportStatus.failed);
      expect(dufs.puts, isEmpty);
      expect(await storedRuns(), isEmpty);

      dufs.listStatus = 207;
      final retry = await makeImporter(dufs).runIfNeeded();
      expect(retry.failures, isEmpty);
      expect(retry.imported, 3);
      expect(dufs.puts, hasLength(1));
    },
  );

  test(
    'one failed download keeps it incomplete; the rest are stored',
    () async {
      final bad = dufs.files.keys.first;
      dufs.failingGets = {bad};

      final report = await makeImporter(dufs).runIfNeeded();

      expect(report.failures.single, contains(bad));
      expect(report.imported, 2);
      expect(dufs.puts, isEmpty);
      expect(runnerUpImportStatus.value, RunnerUpImportStatus.failed);

      dufs.failingGets = {};
      final retry = await makeImporter(dufs).runIfNeeded();
      expect(retry.failures, isEmpty);
      expect(retry.imported, 1);
      expect(retry.duplicates, 2);
      expect(dufs.puts, hasLength(1));
      expect(await storedRuns(), hasLength(3));
    },
  );

  test('an unreachable PC is a failure, not a crash', () async {
    dufs.unreachable = true;
    final report = await makeImporter(dufs).runIfNeeded();
    expect(report.failures.single, contains('network is down'));
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.failed);
  });

  test('a file that is no usable run is skipped for good', () async {
    dufs.files['junk_Running.tcx'] = utf8Bytes('not xml');
    dufs.files['bytes_Running.tcx'] = Uint8List.fromList([0xff, 0xfe, 0xfd]);

    final report = await makeImporter(dufs).runIfNeeded();

    expect(report.failures, isEmpty);
    expect(report.skipped, 2);
    final marker = jsonDecode(dufs.markers.single) as Map<String, dynamic>;
    expect(marker['count'], 3);
    expect(marker['tcx_names'], isNot(contains('junk_Running.tcx')));
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.done);
  });

  test(
    'a failed marker PUT keeps the import and retries only the PUT',
    () async {
      dufs.markerStatus = 500;
      final first = await makeImporter(dufs).runIfNeeded();

      expect(first.failures.single, contains('500'));
      expect(runnerUpImportStatus.value, RunnerUpImportStatus.failed);
      expect(await storedRuns(), hasLength(3));

      dufs.markerStatus = 201;
      dufs.requests.clear();
      final retry = await makeImporter(dufs).runIfNeeded();

      expect(retry.failures, isEmpty);
      expect(dufs.requests, ['PUT /RunnerUp/.workout_app_import.json']);
      expect(runnerUpImportStatus.value, RunnerUpImportStatus.done);
      dufs.requests.clear();
      await makeImporter(dufs).runIfNeeded();
      expect(
        dufs.requests,
        isEmpty,
        reason: 'marker delivered: truly finished',
      );
    },
  );

  test('without a dufs login it fails loudly and fetches nothing', () async {
    final importer = RunnerUpImporter(
      client: dufs.client,
      loadLogin: () async => null,
      canReadStorage: () async => false,
      isAndroid: true,
    );
    final report = await importer.runIfNeeded();
    expect(report.failures.single, contains('no dufs login'));
    expect(dufs.requests, isEmpty);
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.failed);
  });

  test('the login vanishing before the marker PUT is a failure too', () async {
    var calls = 0;
    final importer = RunnerUpImporter(
      client: dufs.client,
      loadLogin: () async => calls++ == 0 ? kLogin : null,
      canReadStorage: () async => false,
      isAndroid: true,
    );
    final report = await importer.runIfNeeded();
    expect(report.failures.single, contains('PC was not told'));
    expect(dufs.puts, isEmpty);
  });

  test('the sandbox never imports', () async {
    Sandbox.enabled = true;
    final report = await makeImporter(dufs).runIfNeeded();
    await SandboxLog.flush();
    expect(report.imported, 0);
    expect(dufs.requests, isEmpty);
    expect(await storedRuns(), isEmpty);
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.idle);
  });

  test('off the phone it does nothing (no early marker)', () async {
    await makeImporter(dufs, android: false).runIfNeeded();
    expect(dufs.requests, isEmpty);
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.idle);
  });

  test('with every default it is inert on the desktop test host', () async {
    final report = await RunnerUpImporter().runIfNeeded();
    expect(report.imported, 0);
    expect(runnerUpImportStatus.value, RunnerUpImportStatus.idle);
  });
}
