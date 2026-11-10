import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_upload_credentials.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '../fake_secure_storage.dart';
import '../run_test_fixtures.dart';

final _login = DufsCredentials(
  url: 'https://cloud.example',
  user: 'workout_app',
  password: 'pw',
);

/// A store that already holds [_login] (or fails like a broken keystore).
class _FixedStore implements RunCredentialStore {
  _FixedStore(this._login, {this.onRead, this.throwing = false});

  final DufsCredentials? _login;
  final Future<void> Function()? onRead;
  final bool throwing;

  @override
  Future<DufsCredentials?> read() async {
    await onRead?.call();
    if (throwing) throw PlatformException(code: 'keystore');
    return _login;
  }

  @override
  Future<ProvisionOutcome> importProvisionFile() => throw UnimplementedError();
}

StorageService get _db => StorageService.instance;

Future<RunRecord> _save(String start) async {
  final track = sampleTrack(start: start);
  await saveRecordedRun(track, storage: _db, enqueue: () async => null);
  return (await _db.listRuns()).firstWhere((r) => r.track.id == track.id);
}

Future<RunUploadState> _stateOf(String id) async =>
    (await _db.getRun(id))!.uploadState;

void main() {
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

  RunUploader uploader(
    http.Client client, {
    RunCredentialStore? store,
    List<Duration>? delays,
    List<void Function()>? timers,
  }) => RunUploader(
    credentials: store ?? _FixedStore(_login),
    client: client,
    scheduler: (d, f) {
      delays?.add(d);
      timers?.add(f);
      return Timer(const Duration(days: 1), f);
    },
  );

  test('a 201 marks the run uploaded after a Basic-auth PUT', () async {
    final run = await _save('2026-11-09T12:00:00Z');
    late http.Request seen;
    final up = uploader(
      MockClient((r) async {
        seen = r;
        return http.Response('', 201);
      }),
    );

    final status = await up.uploadPending();

    expect(seen.method, 'PUT');
    expect(
      seen.url.toString(),
      'https://cloud.example/RunnerUp/${run.tcxFilename}',
    );
    expect(
      seen.headers['Authorization'],
      'Basic ${base64.encode(utf8.encode('workout_app:pw'))}',
    );
    expect(seen.body, encodeTcx((await _db.getRun(run.track.id))!.track));
    expect(status.health, UploadHealth.idle);
    expect(status.pending, 0);
    expect(await _stateOf(run.track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test('a 401 keeps the run pending and retries on a timer', () async {
    final run = await _save('2026-11-09T12:00:00Z');
    final delays = <Duration>[];
    final timers = <void Function()>[];
    var code = 401;
    final up = uploader(
      MockClient((_) async => http.Response('', code)),
      delays: delays,
      timers: timers,
    );

    final status = await up.uploadPending();
    expect(status.health, UploadHealth.retrying);
    expect(status.pending, 1);
    expect(status.reason, contains('401'));
    expect(up.status.value, same(status));
    expect(delays, [kUploadRetryAfter]);
    expect(await _stateOf(run.track.id), RunUploadState.pending);

    code = 201;
    timers.single();
    // Joins the pass the timer just started (single flight).
    await up.uploadPending();
    expect(await _stateOf(run.track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test('a network error or server fault stays pending', () async {
    final run = await _save('2026-11-09T12:00:00Z');
    final broken = uploader(
      MockClient((_) async => throw http.ClientException('no route')),
    );
    final first = await broken.uploadPending();
    expect(first.health, UploadHealth.retrying);
    expect(first.reason, contains('no route'));

    final faulty = uploader(MockClient((_) async => http.Response('', 503)));
    final second = await faulty.uploadPending();
    expect(second.reason, contains('503'));
    expect(second.reason, isNot(contains('provision')));
    expect(await _stateOf(run.track.id), RunUploadState.pending);
    broken.dispose();
    faulty.dispose();
  });

  test('runs go oldest first and a failure stops the pass', () async {
    final older = await _save('2026-11-08T12:00:00Z');
    final newer = await _save('2026-11-09T12:00:00Z');
    final urls = <String>[];
    final up = uploader(
      MockClient((r) async {
        urls.add(r.url.pathSegments.last);
        return http.Response('', 500);
      }),
    );
    final status = await up.uploadPending();
    expect(urls, [older.tcxFilename]);
    expect(status.pending, 2);
    expect(await _stateOf(newer.track.id), RunUploadState.pending);
    up.dispose();
  });

  test(
    'without a provisioned login nothing is sent and no retry runs',
    () async {
      await _save('2026-11-09T12:00:00Z');
      final timers = <void Function()>[];
      var calls = 0;
      final up = uploader(
        MockClient((_) async {
          calls++;
          return http.Response('', 201);
        }),
        store: _FixedStore(null),
        timers: timers,
      );
      final status = await up.uploadPending();
      expect(status.health, UploadHealth.notConfigured);
      expect(status.reason, contains('provision_run_upload.sh'));
      expect(calls, 0);
      expect(timers, isEmpty);
      up.dispose();
    },
  );

  test('the sandbox keeps runs and never opens a connection', () async {
    Sandbox.enabled = true;
    final run = await _save('2026-11-09T12:00:00Z');
    final up = uploader(
      MockClient((_) async => fail('the sandbox must never PUT')),
      store: _FixedStore(_login),
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.sandbox);
    expect(status.pending, 1);
    expect(await _stateOf(run.track.id), RunUploadState.pending);
    up.dispose();
  });

  test('an empty queue is idle', () async {
    final up = uploader(MockClient((_) async => fail('nothing to send')));
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.idle);
    expect(status.pending, 0);
    up.dispose();
  });

  test('concurrent calls share one pass', () async {
    await _save('2026-11-09T12:00:00Z');
    var calls = 0;
    final up = uploader(
      MockClient((_) async {
        calls++;
        return http.Response('', 201);
      }),
    );
    final both = await Future.wait([up.uploadPending(), up.uploadPending()]);
    expect(calls, 1);
    expect(both.first, same(both.last));
    up.dispose();
  });

  test('a stored hash that no longer matches still uploads', () async {
    final track = sampleTrack();
    await _db.insertRun(
      track,
      tcxFilename: tcxFilename(track),
      tcxSha256: 'stale',
      uploadState: RunUploadState.pending,
    );
    var calls = 0;
    final up = uploader(
      MockClient((_) async {
        calls++;
        return http.Response('', 200);
      }),
    );
    await up.uploadPending();
    expect(calls, 1);
    expect(await _stateOf(track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test(
    'a run deleted mid-pass is skipped; one deleted mid-PUT is logged',
    () async {
      final first = await _save('2026-11-08T12:00:00Z');
      final second = await _save('2026-11-09T12:00:00Z');
      final seen = <String>[];
      final up = uploader(
        MockClient((r) async {
          seen.add(r.url.pathSegments.last);
          await _db.deleteRun(second.track.id);
          return http.Response('', 201);
        }),
        store: _FixedStore(
          _login,
          onRead: () async {
            await _db.deleteRun(first.track.id);
          },
        ),
      );
      final status = await up.uploadPending();
      expect(seen, [second.tcxFilename]);
      expect(status.health, UploadHealth.idle);
      up.dispose();
    },
  );

  test('a crashing keystore is reported, not thrown', () async {
    await _save('2026-11-09T12:00:00Z');
    final timers = <void Function()>[];
    final up = uploader(
      MockClient((_) async => fail('no login, no PUT')),
      store: _FixedStore(_login, throwing: true),
      timers: timers,
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.retrying);
    expect(status.reason, contains('crashed'));
    expect(timers, hasLength(1));
    up.dispose();
  });

  test('a queue with no injected client opens and closes its own', () async {
    await _save('2026-11-09T12:00:00Z');
    final up = RunUploader(
      credentials: _FixedStore(
        DufsCredentials(url: 'http://127.0.0.1:1', user: 'u', password: 'p'),
      ),
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.retrying);
    expect(RunUploader.instance.status.value.health, UploadHealth.idle);
    up.dispose();
  });

  group('provisioning', () {
    late Directory dir;
    setUp(() {
      installFakeSecureStorage();
      dir = Directory.systemTemp.createTempSync('provision_test_');
      addTearDown(() => dir.deleteSync(recursive: true));
    });

    RunCredentialStore store() =>
        RunCredentialStore(externalDir: () async => dir);
    File file() => File('${dir.path}/$kProvisionFileName');

    test('a login file is imported into secure storage and deleted', () async {
      file().writeAsStringSync(
        jsonEncode({
          'url': 'https://cloud.example/',
          'user': 'workout_app',
          'password': 'secret',
        }),
      );
      final s = store();
      expect(await s.read(), isNull);

      final outcome = await s.importProvisionFile();

      expect(outcome.status, ProvisionStatus.imported);
      expect(file().existsSync(), isFalse);
      final login = (await s.read())!;
      expect(login.url, 'https://cloud.example');
      expect(login.user, 'workout_app');
      expect(login.password, 'secret');
      expect(
        login.authorization,
        'Basic ${base64.encode(utf8.encode('workout_app:secret'))}',
      );
    });

    test('no file, or no directory, is a quiet no-op', () async {
      expect(
        (await store().importProvisionFile()).status,
        ProvisionStatus.absent,
      );
      final none = RunCredentialStore(externalDir: () async => null);
      expect((await none.importProvisionFile()).status, ProvisionStatus.absent);
      // The default directory lookup answers null off Android.
      expect(
        (await RunCredentialStore().importProvisionFile()).status,
        ProvisionStatus.absent,
      );
    });

    test('an unusable file is kept and reported', () async {
      final bad = <String>[
        'not json',
        '[]',
        jsonEncode({'url': 'https://x', 'user': 'u'}),
        jsonEncode({'url': 'ftp://x', 'user': 'u', 'password': 'p'}),
        jsonEncode({'url': 'nonsense', 'user': 'u', 'password': 'p'}),
        jsonEncode({'url': 'https://x', 'user': '', 'password': 'p'}),
        jsonEncode({'url': 'https://x', 'user': 'u', 'password': ''}),
      ];
      for (final text in bad) {
        file().writeAsStringSync(text);
        final s = store();
        final outcome = await s.importProvisionFile();
        expect(outcome.status, ProvisionStatus.invalid, reason: text);
        expect(outcome.reason, contains('provision_run_upload.sh'));
        expect(file().existsSync(), isTrue);
        expect(await s.read(), isNull);
      }
    });
  });

  group('saveRecordedRun', () {
    test('stores a pending app run and starts the upload', () async {
      var enqueued = 0;
      final track = sampleTrack();
      final result = await saveRecordedRun(
        track,
        storage: _db,
        enqueue: () async {
          enqueued++;
          return null;
        },
      );
      expect(result.stored, isTrue);
      expect(enqueued, 1);
      final record = (await _db.getRun(track.id))!;
      expect(record.uploadState, RunUploadState.pending);
      expect(record.track.points, hasLength(3));
      expect(record.tcxFilename, endsWith('_Running.tcx'));
    });

    test('a run already stored is reported and not queued twice', () async {
      var enqueued = 0;
      Future<Object?> enqueue() async {
        enqueued++;
        return null;
      }

      final track = sampleTrack();
      await saveRecordedRun(track, storage: _db, enqueue: enqueue);
      final again = await saveRecordedRun(
        track,
        storage: _db,
        enqueue: enqueue,
      );
      expect(again.stored, isFalse);
      expect(again.reason, contains('already stored'));
      expect(enqueued, 1);
    });
  });
}
