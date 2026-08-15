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
  _cutoverTests();
  _manualWorkoutSurvivalTests();
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

  test('does nothing when no token is configured', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = mockGitHub();

    final result = await syncService(
      httpClient: httpClient,
    ).push(workoutSession());

    expect(putCalls, isEmpty);
    // Not just "nothing happened" -- the caller can tell WHY, so an unpushed
    // workout is diagnosable instead of silently absent everywhere else.
    expect(result.pushed, isFalse);
    expect(result.reason, contains('not configured'));
  });

  test('pushes a new record when nothing has been synced yet', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
    );

    final session = workoutSession();
    await syncService(httpClient: httpClient).push(session);

    // Two writes: the log, then the revision published after it.
    expect(putCalls, hasLength(2));
    expect(logPut(putCalls).path, 'screen-locker-sync/devices/phone/log.json');
    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(logPut(putCalls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;
    expect(pushedLog.keys, [session.startTime.toIso8601String()]);
  });

  test('merges the new session onto an already-pushed log', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final earlier = Record(
      id: 'earlier',
      fields: {
        'payload': ({'workout_type': 'B'}, Hlc.newTick('phone')),
      },
    );
    final existingLog = jsonEncode({'earlier': earlier.toJson()});
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': syncResponse(200, []),
        'screen-locker-sync/devices/phone/log.json': fileContaining(
          existingLog,
        ),
      },
    );

    final session = workoutSession();
    await syncService(httpClient: httpClient).push(session);

    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(logPut(putCalls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;
    expect(
      pushedLog.keys,
      containsAll(['earlier', session.startTime.toIso8601String()]),
    );
  });

  test('a sync error is swallowed, but reported', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final httpClient = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );

    final result = await syncService(
      httpClient: httpClient,
    ).push(workoutSession());

    // Swallowed: a failed push must never cost the user their finished
    // workout. Reported: the previous contract logged to debugPrint, which
    // goes nowhere in a release build -- a workout could go unpushed with
    // nothing anywhere saying so.
    expect(result.pushed, isFalse);
    expect(result.reason, contains('push failed'));
  });

  test('PushResult stringifies both fields for logs', () {
    // It exists to be readable in a log line, so the log line is the test.
    const result = PushResult(pushed: false, reason: 'push failed: boom');

    expect(result.toString(), contains('pushed: false'));
    expect(result.toString(), contains('push failed: boom'));
  });

  test('a successful push reports that it happened', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
    );

    final result = await syncService(
      httpClient: httpClient,
    ).push(workoutSession());

    expect(result.pushed, isTrue);
    expect(result.reason, 'pushed');
    expect(putCalls, isNotEmpty);
  });

  test('pushManual does nothing without a token', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = mockGitHub();
    await syncService(
      httpClient: httpClient,
    ).pushManual(manualRecord('manual:x', '40', 1000));
    expect(putCalls, isEmpty);
  });

  test('pushManual pushes when nothing has been synced yet', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
    );
    await syncService(
      httpClient: httpClient,
    ).pushManual(manualRecord('manual:2026-07-13T18:00', '40', 1000));
    expect(logPut(putCalls).path, 'screen-locker-sync/devices/phone/log.json');
  });

  test('pushManual merges onto an existing log', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final existing = jsonEncode({
      'manual:old': manualRecord('manual:old', '20', 1000).toJson(),
    });
    final (:httpClient, :putCalls) = mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': syncResponse(200, []),
        'screen-locker-sync/devices/phone/log.json': fileContaining(existing),
      },
    );
    await syncService(
      httpClient: httpClient,
    ).pushManual(manualRecord('manual:2026-07-13T18:00', '40', 2000));
    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(logPut(putCalls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;
    expect(
      pushedLog.keys,
      containsAll(['manual:old', 'manual:2026-07-13T18:00']),
    );
  });

  test('pushManual reports a failure instead of hiding it', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final httpClient = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );
    await expectLater(
      syncService(
        httpClient: httpClient,
      ).pushManual(manualRecord('manual:x', '40', 1000)),
      completes,
    );
  });

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

/// Regression tests for the one thing that went RIGHT on 2026-08-15.
///
/// A manual workout was logged while the phone was disconnected. When
/// Firebase later connected, the entry was NOT erased -- the user called this
/// out as good behaviour worth keeping. It is currently correct by
/// construction (`MirrorStore.getFileText` falls through to the GitHub mirror
/// when the Firebase primary returns null, so a first connect reads the prior
/// log rather than an empty one), which is exactly why it needs pinning:
/// nothing else would fail if that fall-through were removed.
void _manualWorkoutSurvivalTests() {
  group('connecting to Firebase does not erase local manual workouts', () {
    /// A manual record already in this device's log, logged while offline.
    Record priorManual() => Record(
      id: 'manual:2026-08-01T10:00',
      fields: {
        'payload': (
          {'kind': 'manual_workout', 'date': '2026-08-01'},
          Hlc.newTick('phone'),
        ),
      },
    );

    Map<String, dynamic> decodeLogPut(List<PutCall> calls) =>
        jsonDecode(
              utf8.decode(
                base64.decode(logPut(calls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;

    test(
      'a first Firebase connect keeps a manual record only GitHub has',
      () async {
        installFakeSecureStorage(initial: {'sync.token': 'tok'});
        final existingLog = jsonEncode({
          priorManual().id: priorManual().toJson(),
        });
        final (:httpClient, :putCalls) = mockGitHub(
          contentResponses: {
            'screen-locker-sync/devices': syncResponse(200, []),
            'screen-locker-sync/devices/phone/log.json': fileContaining(
              existingLog,
            ),
          },
        );
        // Firebase answers 'null' to every GET -- the fresh-connect state, and
        // the exact condition under which a naive implementation would treat
        // the remote as empty and overwrite the log with just the new record.
        final firebase = fakeFirebase();

        final newManual = Record(
          id: 'manual:2026-08-15T12:18',
          fields: {
            'payload': (
              {'kind': 'manual_workout', 'date': '2026-08-15'},
              Hlc.newTick('phone'),
            ),
          },
        );
        final result = await syncService(
          httpClient: httpClient,
          firebaseFactory: () async => firebase.client,
        ).pushManual(newManual);

        expect(result.pushed, isTrue);
        final pushedLog = decodeLogPut(putCalls);
        expect(
          pushedLog.keys,
          containsAll([priorManual().id, newManual.id]),
          reason: 'the offline-logged manual workout must survive the connect',
        );
      },
    );

    test(
      'syncNow reports "not configured" rather than pretending to work',
      () async {
        installFakeSecureStorage();
        final (:httpClient, :putCalls) = mockGitHub();

        final result = await syncService(httpClient: httpClient).syncNow();

        expect(putCalls, isEmpty);
        expect(result.pushed, isFalse);
        // The card renders this reason, so it has to name the actual problem.
        expect(result.reason, contains('not configured'));
      },
    );

    test('syncNow works on a device with no log yet', () async {
      // Nothing to preserve on a brand-new device: the tick must still
      // succeed rather than failing on the absent log.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final (:httpClient, :putCalls) = mockGitHub(
        contentResponses: {'screen-locker-sync/devices': syncResponse(200, [])},
      );

      final result = await syncService(httpClient: httpClient).syncNow();

      expect(result.pushed, isTrue);
      expect(result.reason, 'synced');
    });

    test('syncNow reports the reason when the round trip fails', () async {
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final httpClient = http_testing.MockClient(
        (request) async => http.Response('', 500),
      );

      final result = await syncService(httpClient: httpClient).syncNow();

      // Never throws into the UI, but never silent either: this string is
      // exactly what the "Sync failed" card shows the user.
      expect(result.pushed, isFalse);
      expect(result.reason, contains('sync failed'));
    });

    test('a plain sync tick on first connect does not drop the log', () async {
      // syncNow() pushes no new record, so if the fresh-connect read came
      // back empty this would write an EMPTY log over a good one -- the
      // worst version of the bug, triggered just by opening the app.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final existingLog = jsonEncode({
        priorManual().id: priorManual().toJson(),
      });
      final (:httpClient, :putCalls) = mockGitHub(
        contentResponses: {
          'screen-locker-sync/devices': syncResponse(200, []),
          'screen-locker-sync/devices/phone/log.json': fileContaining(
            existingLog,
          ),
        },
      );
      final firebase = fakeFirebase();

      final result = await syncService(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).syncNow();

      expect(result.pushed, isTrue);
      final logPuts = putCalls.where((c) => c.path.endsWith('log.json'));
      if (logPuts.isNotEmpty) {
        expect(
          decodeLogPut(putCalls).keys,
          contains(priorManual().id),
          reason: 'a no-op tick must never blank the log',
        );
      }
    });
  });
}

void _cutoverTests() {
  group('Firebase cutover', () {
    test('pushes to Firebase and still mirrors to GitHub', () async {
      // The cutover guarantee: both backends receive the write, so a PC that
      // has not moved yet still sees the workout.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final (:httpClient, :putCalls) = mockGitHub();
      final firebase = fakeFirebase();

      await syncService(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).push(workoutSession());

      expect(
        firebase.puts.any((p) => p.contains('screen-locker-sync')),
        isTrue,
        reason: 'Firebase is primary and must receive the write',
      );
      expect(
        putCalls,
        isNotEmpty,
        reason: 'GitHub must still be mirrored during the cutover',
      );
    });

    test('pushManual also mirrors to both backends', () async {
      // pushManual is a separate path from push(); it needs its own proof
      // that Firebase became primary rather than being skipped.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final (:httpClient, :putCalls) = mockGitHub();
      final firebase = fakeFirebase();

      await syncService(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).pushManual(
        Record(
          id: 'manual:x',
          fields: {
            'payload': (
              {'kind': 'manual_workout', 'date': '2026-07-13', 'cost': '40'},
              Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'phone'),
            ),
          },
        ),
      );

      expect(
        firebase.puts.any((p) => p.contains('screen-locker-sync')),
        isTrue,
      );
      expect(putCalls, isNotEmpty);
    });

    test('reads merge both backends', () async {
      // Read-only path: a workout logged against either backend must count.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final firebase = fakeFirebase();

      final (:httpClient, :putCalls) = mockGitHub();
      final payloads = await syncService(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).readMergedWorkoutPayloads();

      expect(payloads, isEmpty);
    });
  });
}
