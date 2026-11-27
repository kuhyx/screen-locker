/// Offline-first: a finished workout survives a dead network and goes out by
/// itself on the next tick.
///
/// The PC credits a workout once per `{type}:{date}` (see
/// `screen_locker/_log_mixin.py:_derive_workout_id` and
/// `test_session_sync.py::test_is_idempotent_across_repeated_syncs`), so a
/// re-push is safe there; these tests pin the phone half: the re-push carries
/// the very same record (same id, same clock), never a fresh copy.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/services/workout_sync_session.dart';

import '../fake_secure_storage.dart';
import '_sync_remote_fixture.dart';
import '_sync_test_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('a push that failed goes out with the next sync tick', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote()..down = true;
    final session = workoutSession();

    final failed = await syncService(httpClient: remote.client()).push(session);
    expect(failed.pushed, isFalse);

    remote.down = false;
    final synced = await syncService(httpClient: remote.client()).syncNow();

    expect(synced.pushed, isTrue);
    expect(remote.logPuts.last.keys, contains(workoutRecordId(session)));
  });

  test('a workout finished before sync was set up goes out later', () async {
    installFakeSecureStorage();
    final remote = FakeRemote();
    final session = workoutSession();

    final skipped = await syncService(
      httpClient: remote.client(),
    ).push(session);
    expect(skipped.reason, contains('not configured'));

    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    await syncService(httpClient: remote.client()).syncNow();

    expect(remote.logPuts.last.keys, contains(workoutRecordId(session)));
  });

  test('the re-push carries the same record, not a new copy', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote()..down = true;
    final session = workoutSession();
    await syncService(httpClient: remote.client()).push(session);
    remote.down = false;

    await syncService(httpClient: remote.client()).syncNow();
    final first = remote.logPuts.last[workoutRecordId(session)];
    await syncService(httpClient: remote.client()).syncNow();

    // Byte-identical record: one id, one clock. The PC sees nothing new.
    final records = remote.logPuts.expand((log) => log.keys).toSet();
    expect(records, {workoutRecordId(session)});
    expect(remote.logPuts.last[workoutRecordId(session)], first);
  });

  test('overlapping ticks run one after another, the last one complete', () {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote();
    final session = workoutSession();

    return Future.wait([
      syncService(httpClient: remote.client()).syncNow(),
      syncService(httpClient: remote.client()).push(session),
    ]).then((results) {
      expect(results.every((r) => r.pushed), isTrue);
      expect(remote.logPuts.last.keys, contains(workoutRecordId(session)));
    });
  });

  test('a tick that never answers is cut off and frees the queue', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final saved = WorkoutSyncSession.tickTimeout;
    WorkoutSyncSession.tickTimeout = const Duration(milliseconds: 50);
    addTearDown(() => WorkoutSyncSession.tickTimeout = saved);
    final hanging = http_testing.MockClient(
      (_) => Completer<http.Response>().future,
    );
    final remote = FakeRemote();

    final hung = syncService(httpClient: hanging).push(workoutSession());
    // Let the push keep its record and take the queue before the next tick.
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final results = await Future.wait([
      hung,
      syncService(httpClient: remote.client()).syncNow(),
    ]);

    expect(results.first.pushed, isFalse);
    expect(results.first.reason, contains('no answer'));
    // The record the hung push kept goes out with the tick queued behind it.
    expect(results.last.pushed, isTrue);
    expect(
      remote.logPuts.last.keys,
      contains(workoutRecordId(workoutSession())),
    );
  });
}
