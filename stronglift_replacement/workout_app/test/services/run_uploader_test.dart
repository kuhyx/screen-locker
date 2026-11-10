import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

import 'run_uploader_support.dart';

void main() {
  useUploaderStorage();

  test('a 201 marks the run uploaded after a Basic-auth PUT', () async {
    final run = await saveRun('2026-11-09T12:00:00Z');
    late http.Request seen;
    final up = uploaderFor(
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
    expect(seen.body, encodeTcx((await db.getRun(run.track.id))!.track));
    expect(status.health, UploadHealth.idle);
    expect(status.pending, 0);
    expect(await stateOf(run.track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test('a 401 keeps the run pending and retries on a timer', () async {
    final run = await saveRun('2026-11-09T12:00:00Z');
    final delays = <Duration>[];
    final timers = <void Function()>[];
    var code = 401;
    final up = uploaderFor(
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
    expect(await stateOf(run.track.id), RunUploadState.pending);

    code = 201;
    timers.single();
    // Joins the pass the timer just started (single flight).
    await up.uploadPending();
    expect(await stateOf(run.track.id), RunUploadState.uploaded);
    up.dispose();
  });

  test('a network error or server fault stays pending', () async {
    final run = await saveRun('2026-11-09T12:00:00Z');
    final broken = uploaderFor(
      MockClient((_) async => throw http.ClientException('no route')),
    );
    final first = await broken.uploadPending();
    expect(first.health, UploadHealth.retrying);
    expect(first.reason, contains('no route'));

    final faulty = uploaderFor(MockClient((_) async => http.Response('', 503)));
    final second = await faulty.uploadPending();
    expect(second.reason, contains('503'));
    expect(second.reason, isNot(contains('provision')));
    expect(await stateOf(run.track.id), RunUploadState.pending);
    broken.dispose();
    faulty.dispose();
  });

  test('runs go oldest first and a failure stops the pass', () async {
    final older = await saveRun('2026-11-08T12:00:00Z');
    final newer = await saveRun('2026-11-09T12:00:00Z');
    final urls = <String>[];
    final up = uploaderFor(
      MockClient((r) async {
        urls.add(r.url.pathSegments.last);
        return http.Response('', 500);
      }),
    );
    final status = await up.uploadPending();
    expect(urls, [older.tcxFilename]);
    expect(status.pending, 2);
    expect(await stateOf(newer.track.id), RunUploadState.pending);
    up.dispose();
  });

  test(
    'without a provisioned login nothing is sent and no retry runs',
    () async {
      await saveRun('2026-11-09T12:00:00Z');
      final timers = <void Function()>[];
      var calls = 0;
      final up = uploaderFor(
        MockClient((_) async {
          calls++;
          return http.Response('', 201);
        }),
        store: FixedStore(null),
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
}
