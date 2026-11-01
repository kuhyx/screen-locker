// The real crdt_sync read/push behind the export's manual_workouts.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/manual_workout_port.dart';

import '../fake_secure_storage.dart';
import '_sync_test_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final manual = manualRecord('manual:2026-07-13T10:00', 'NEW', 2000);
  const session = Record(
    id: '2026-07-05T09:00:00',
    fields: {
      'payload': (
        {'workout_type': 'A'},
        Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'pc'),
      ),
    },
  );
  const tomb = Record(
    id: 'manual:2026-07-01T09:00',
    fields: {},
    deleted: true,
    deletedHlc: Hlc(wallTimeMs: 3000, counter: 0, nodeId: 'pc'),
  );

  test('read is null when sync is not configured', () async {
    installFakeSecureStorage();
    final (:httpClient, putCalls: _) = mockGitHub();
    final port = SyncManualWorkoutPort(syncService(httpClient: httpClient));
    expect(await port.read(), isNull);
  });

  test('read is null when the backend errors', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, putCalls: _) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(500)},
    );
    final port = SyncManualWorkoutPort(syncService(httpClient: httpClient));
    expect(await port.read(), isNull);
  });

  test('read returns manual records and tombstones, not sessions', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final phone = jsonEncode({
      manual.id: manual.toJson(),
      session.id: session.toJson(),
    });
    final pc = jsonEncode({tomb.id: tomb.toJson()});
    final (:httpClient, putCalls: _) = mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': syncResponse(200, [
          {'name': 'phone'},
          {'name': 'pc'},
        ]),
        'screen-locker-sync/devices/phone/log.json': fileContaining(phone),
        'screen-locker-sync/devices/pc/log.json': fileContaining(pc),
      },
    );
    final port = SyncManualWorkoutPort(syncService(httpClient: httpClient));

    final log = await port.read();

    expect(log!.keys.toSet(), {manual.id, tomb.id});
    expect(log[tomb.id]!.deleted, true);
  });

  test('push merges the records into this device log', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
    );
    final port = SyncManualWorkoutPort(syncService(httpClient: httpClient));

    expect(await port.push({manual.id: manual}), true);

    final body = utf8.decode(
      base64.decode(logPut(putCalls).body['content'] as String),
    );
    expect((jsonDecode(body) as Map).keys, contains(manual.id));
  });

  test('push reports failure instead of throwing when unconfigured', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = mockGitHub();
    final port = SyncManualWorkoutPort(syncService(httpClient: httpClient));
    expect(await port.push({manual.id: manual}), false);
    expect(putCalls, isEmpty);
  });

  test('read mirrors through Firebase and returns an empty log', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, putCalls: _) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
    );
    final firebase = fakeFirebase().client;
    final port = SyncManualWorkoutPort(
      syncService(
        httpClient: httpClient,
        firebaseFactory: () async => firebase,
      ),
    );
    expect(await port.read(), isEmpty);
  });

  test('the default port builds its own sync service', () {
    expect(SyncManualWorkoutPort(), isA<ManualWorkoutPort>());
  });

  test('the offline port reads null and refuses pushes', () async {
    const port = OfflineManualWorkoutPort();
    expect(await port.read(), isNull);
    expect(await port.push({manual.id: manual}), false);
  });
}
