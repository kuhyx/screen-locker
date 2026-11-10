import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_upload_credentials.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';

import '../run_test_fixtures.dart';

final testLogin = DufsCredentials(
  url: 'https://cloud.example',
  user: 'workout_app',
  password: 'pw',
);

/// A store that already holds [testLogin] (or fails like a broken keystore).
class FixedStore implements RunCredentialStore {
  FixedStore(this._creds, {this.onRead, this.throwing = false});

  final DufsCredentials? _creds;
  final Future<void> Function()? onRead;
  final bool throwing;

  @override
  Future<DufsCredentials?> read() async {
    await onRead?.call();
    if (throwing) throw PlatformException(code: 'keystore');
    return _creds;
  }

  @override
  Future<ProvisionOutcome> importProvisionFile() => throw UnimplementedError();
}

StorageService get db => StorageService.instance;

Future<RunRecord> saveRun(String start) async {
  final track = sampleTrack(start: start);
  await saveRecordedRun(track, storage: db, enqueue: () async => null);
  return (await db.listRuns()).firstWhere((r) => r.track.id == track.id);
}

Future<RunUploadState> stateOf(String id) async =>
    (await db.getRun(id))!.uploadState;

/// Opens a fresh in-memory run database around every test.
void useUploaderStorage() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  tearDown(() {
    Sandbox.enabled = false;
    StorageService.resetForTesting();
  });
}

/// An uploader over [client] whose retry timer never fires on its own.
RunUploader uploaderFor(
  http.Client client, {
  RunCredentialStore? store,
  List<Duration>? delays,
  List<void Function()>? timers,
}) => RunUploader(
  credentials: store ?? FixedStore(testLogin),
  client: client,
  scheduler: (d, f) {
    delays?.add(d);
    timers?.add(f);
    return Timer(const Duration(days: 1), f);
  },
);
