/// Offline-first: everything a tick or a live read pulled is kept locally and
/// readable with the network gone.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/workout_log_store.dart';
import 'package:workout_app/services/workout_sync_service.dart';

import '../fake_secure_storage.dart';
import '_sync_remote_fixture.dart';
import '_sync_test_fixtures.dart';

/// A local log whose disk is gone: reading its records and every write throw.
class _BrokenStore extends LogStore {
  _BrokenStore() : super(persistence: _NoPersistence(), nodeId: 'phone');

  @override
  Iterable<Record> get values => throw const FileSystemException('gone');

  @override
  Future<void> upsert(Record record) async =>
      throw const FileSystemException('gone');

  @override
  Future<void> replaceAll(Log merged) async =>
      throw const FileSystemException('gone');
}

class _NoPersistence implements LogPersistence {
  @override
  Future<String?> read() async => null;

  @override
  Future<void> write(String text) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('records a tick pulled stay readable with the network gone', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote();
    remote.files['screen-locker-sync/devices/pc/log.json'] = jsonEncode({
      pcRunRecord().id: pcRunRecord().toJson(),
    });
    await syncService(httpClient: remote.client()).syncNow();

    remote.down = true;
    // A store reopened from disk: what the next app launch reads.
    final cached = await syncService(
      httpClient: remote.client(),
      logStore: await openWorkoutLogStoreIn(workoutLogDirOverride!),
    ).readCachedWorkoutPayloads();

    expect(cached.map((p) => p['kind']), contains('runnerup_verified'));
  });

  test('a live history read is kept for the next offline read', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote();
    remote.files['screen-locker-sync/devices/pc/log.json'] = jsonEncode({
      pcRunRecord().id: pcRunRecord().toJson(),
    });
    final live = await syncService(
      httpClient: remote.client(),
    ).readMergedWorkoutPayloads();
    expect(live, hasLength(1));

    remote.down = true;
    final cached = await syncService(
      httpClient: remote.client(),
    ).readCachedWorkoutPayloads();

    expect(cached.map((p) => p['date']), ['2026-07-13']);
  });

  test('a broken local log never breaks a push or a read', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final remote = FakeRemote();
    remote.files['screen-locker-sync/devices/pc/log.json'] = jsonEncode({
      pcRunRecord().id: pcRunRecord().toJson(),
    });
    WorkoutSyncService broken() =>
        syncService(httpClient: remote.client(), logStore: _BrokenStore());

    // The push still reaches the remote; only the local copy is lost.
    final pushed = await broken().push(workoutSession());
    final live = await broken().readMergedWorkoutPayloads();
    final cached = await broken().readCachedWorkoutPayloads();

    expect(pushed.pushed, isTrue);
    expect(remote.logPuts, isNotEmpty);
    // The PC's run plus the workout just pushed: the remote has both.
    expect(live, hasLength(2));
    expect(cached, isEmpty);
  });
}
