import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '../run_test_fixtures.dart';
import 'run_uploader_support.dart';

void main() {
  useUploaderStorage();

  test('the sandbox keeps runs and never opens a connection', () async {
    Sandbox.enabled = true;
    final run = await saveRun('2026-11-09T12:00:00Z');
    final up = uploaderFor(
      MockClient((_) async => fail('the sandbox must never PUT')),
      store: FixedStore(testLogin),
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.sandbox);
    expect(status.pending, 1);
    expect(await stateOf(run.track.id), RunUploadState.pending);
    up.dispose();
  });

  test('an empty queue is idle', () async {
    final up = uploaderFor(MockClient((_) async => fail('nothing to send')));
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.idle);
    expect(status.pending, 0);
    up.dispose();
  });

  test('concurrent calls share one pass', () async {
    await saveRun('2026-11-09T12:00:00Z');
    var calls = 0;
    final up = uploaderFor(
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
    await db.insertRun(
      track,
      tcxFilename: tcxFilename(track),
      tcxSha256: 'stale',
      uploadState: RunUploadState.pending,
    );
    var calls = 0;
    final up = uploaderFor(
      MockClient((_) async {
        calls++;
        return http.Response('', 200);
      }),
    );
    await up.uploadPending();
    expect(calls, 1);
    expect(await stateOf(track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test(
    'a run deleted mid-pass is skipped; one deleted mid-PUT is logged',
    () async {
      final first = await saveRun('2026-11-08T12:00:00Z');
      final second = await saveRun('2026-11-09T12:00:00Z');
      final seen = <String>[];
      final up = uploaderFor(
        MockClient((r) async {
          seen.add(r.url.pathSegments.last);
          await db.deleteRun(second.track.id);
          return http.Response('', 201);
        }),
        store: FixedStore(
          testLogin,
          onRead: () async {
            await db.deleteRun(first.track.id);
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
    await saveRun('2026-11-09T12:00:00Z');
    final timers = <void Function()>[];
    final up = uploaderFor(
      MockClient((_) async => fail('no login, no PUT')),
      store: FixedStore(testLogin, throwing: true),
      timers: timers,
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.retrying);
    expect(status.reason, contains('crashed'));
    expect(timers, hasLength(1));
    up.dispose();
  });

  test('a queue with no injected client opens and closes its own', () async {
    await saveRun('2026-11-09T12:00:00Z');
    final up = RunUploader(
      credentials: FixedStore(
        DufsCredentials(url: 'http://127.0.0.1:1', user: 'u', password: 'p'),
      ),
    );
    final status = await up.uploadPending();
    expect(status.health, UploadHealth.retrying);
    expect(RunUploader.instance.status.value.health, UploadHealth.idle);
    up.dispose();
  });
}
