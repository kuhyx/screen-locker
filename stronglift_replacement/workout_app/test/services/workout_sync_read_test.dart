// Reading merged workout/manual payloads back off the sync backend, and the
// token-recovery path that a rejected token takes.
//
// Split out of workout_sync_service_test.dart, which holds the push side.
import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/services/workout_sync_service.dart';

import '../fake_secure_storage.dart';
import '_sync_test_fixtures.dart';

void main() {
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

  test('readMergedManualPayloads is empty without a token', () async {
    installFakeSecureStorage();
    final (:httpClient, putCalls: _) = mockGitHub();
    expect(
      await syncService(
        httpClient: httpClient,
      ).readMergedManualPayloads(),
      isEmpty,
    );
  });

  test('readMergedManualPayloads merges manuals and skips the rest', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final session = Record(
      id: 's',
      fields: {
        'payload': (
          {'workout_type': 'A'},
          Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'phone'),
        ),
      },
    );
    final noPayload = Record(
      id: 'np',
      fields: {
        'other': (1, Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'phone')),
      },
    );
    final phoneLog = jsonEncode({
      'manual:a': manualRecord('manual:a', 'NEW', 2000).toJson(),
      's': session.toJson(),
      'np': noPayload.toJson(),
    });
    final pcLog = jsonEncode({
      // Same id, older clock -> must lose to phone's newer copy.
      'manual:a': manualRecord('manual:a', 'OLD', 1000).toJson(),
    });
    final (:httpClient, putCalls: _) = mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': syncResponse(200, [
          {'name': 'phone'},
          {'name': 'pc'},
          {'name': 'empty'}, // its log.json 404s -> skipped
        ]),
        'screen-locker-sync/devices/phone/log.json': fileContaining(phoneLog),
        'screen-locker-sync/devices/pc/log.json': fileContaining(pcLog),
      },
    );
    final payloads = await WorkoutSyncService(
      httpClient: httpClient,
    ).readMergedManualPayloads();
    expect(payloads, hasLength(1));
    expect(payloads.single['cost'], 'NEW');
  });

  test('readMergedWorkoutPayloads returns the PC runs too', () async {
    // The PC publishes its whole workout_log.json, so the phone must be able
    // to see verified runs — not just manual self-reports — or the two
    // devices never show the same history.
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final run = Record(
      id: 'runnerup_verified:2026-07-13',
      fields: {
        'payload': (
          {
            'kind': 'runnerup_verified',
            'date': '2026-07-13',
            'source': 'Running: 9.8 km in 55 min',
          },
          Hlc(wallTimeMs: 3000, counter: 0, nodeId: 'pc'),
        ),
      },
    );
    final pcLog = jsonEncode({
      'manual:a': manualRecord('manual:a', 'NEW', 2000).toJson(),
      'runnerup_verified:2026-07-13': run.toJson(),
    });
    final (:httpClient, putCalls: _) = mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': syncResponse(200, [
          {'name': 'pc'},
        ]),
        'screen-locker-sync/devices/pc/log.json': fileContaining(pcLog),
      },
    );
    final service = syncService(httpClient: httpClient);

    final all = await service.readMergedWorkoutPayloads();
    expect(all, hasLength(2));
    expect(
      all.map((p) => p['kind']),
      containsAll(<String>['manual_workout', 'runnerup_verified']),
    );
  });

  test(
    'readMergedManualPayloads still excludes runs (budget stays manual)',
    () async {
      // A verified run must never consume the manual self-report budget.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final run = Record(
        id: 'runnerup_verified:2026-07-13',
        fields: {
          'payload': (
            {'kind': 'runnerup_verified', 'date': '2026-07-13'},
            Hlc(wallTimeMs: 3000, counter: 0, nodeId: 'pc'),
          ),
        },
      );
      final pcLog = jsonEncode({
        'manual:a': manualRecord('manual:a', 'NEW', 2000).toJson(),
        'runnerup_verified:2026-07-13': run.toJson(),
      });
      final (:httpClient, putCalls: _) = mockGitHub(
        contentResponses: {
          'screen-locker-sync/devices': syncResponse(200, [
            {'name': 'pc'},
          ]),
          'screen-locker-sync/devices/pc/log.json': fileContaining(pcLog),
        },
      );
      final manuals = await WorkoutSyncService(
        httpClient: httpClient,
      ).readMergedManualPayloads();
      expect(manuals, hasLength(1));
      expect(manuals.single['kind'], 'manual_workout');
    },
  );

  test('readMergedManualPayloads swallows a sync error', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final httpClient = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );
    expect(
      await syncService(
        httpClient: httpClient,
      ).readMergedManualPayloads(),
      isEmpty,
    );
  });

  test('recovers from the backup when the stored token is rejected', () async {
    // A stale keystore token shadows a good backup (load() only falls back
    // when the keystore is EMPTY), which would leave history silently empty.
    final tempDir = Directory.systemTemp.createTempSync('sync_recover_');
    BackupService.baseDirForTesting = tempDir.path;
    addTearDown(() {
      BackupService.baseDirForTesting = kBackupDir;
      tempDir.deleteSync(recursive: true);
    });

    installFakeSecureStorage(initial: {'sync.token': 'stale'});
    await const SyncSettings(token: 'good').save();
    installFakeSecureStorage(initial: {'sync.token': 'stale'});

    final pcLog = jsonEncode({
      'manual:a': manualRecord('manual:a', 'NEW', 2000).toJson(),
    });
    final httpClient = http_testing.MockClient((req) async {
      if (req.headers['Authorization']?.contains('good') != true) {
        return http.Response('Bad credentials', 401);
      }
      if (req.url.path.endsWith('screen-locker-sync/devices')) {
        return http.Response(
          jsonEncode([
            {'name': 'pc', 'type': 'dir'},
          ]),
          200,
        );
      }
      return http.Response(
        jsonEncode({
          'content': base64Encode(utf8.encode(pcLog)),
          'sha': 'sha',
        }),
        200,
      );
    });

    final payloads = await WorkoutSyncService(
      httpClient: httpClient,
    ).readMergedManualPayloads();

    expect(payloads, hasLength(1));
    expect((await SyncSettings.load()).token, 'good');
  });

  test('reports the failure when the backup token is rejected too', () async {
    final tempDir = Directory.systemTemp.createTempSync('sync_recover_fail_');
    BackupService.baseDirForTesting = tempDir.path;
    addTearDown(() {
      BackupService.baseDirForTesting = kBackupDir;
      tempDir.deleteSync(recursive: true);
    });

    installFakeSecureStorage(initial: {'sync.token': 'stale'});
    await const SyncSettings(token: 'also-bad').save();
    installFakeSecureStorage(initial: {'sync.token': 'stale'});

    // Every token 401s, so the recovery retry fails too.
    final httpClient = http_testing.MockClient(
      (req) async => http.Response('Bad credentials', 401),
    );

    expect(
      await syncService(httpClient: httpClient).readMergedManualPayloads(),
      isEmpty,
    );
  });
}
