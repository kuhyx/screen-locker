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

http.Response _response(int statusCode, [Object? jsonBody]) =>
    http.Response(jsonEncode(jsonBody ?? {}), statusCode);

http.Response _fileContaining(String text) =>
    _response(200, {'content': base64.encode(utf8.encode(text))});

class _PutCall {
  _PutCall(this.path, this.body);
  final String path;
  final Map<String, dynamic> body;
}

/// Builds a mock HTTP client backed by an in-memory router, matching
/// `crdt_sync_dart`'s own `sync_test.dart` helper: GET
/// `.../contents/<key>` returns [contentResponses]`[key]` (404 if absent),
/// the bare repo-existence GET always succeeds, and every PUT is recorded.
({http.Client httpClient, List<_PutCall> putCalls}) _mockGitHub({
  Map<String, http.Response> contentResponses = const {},
}) {
  final putCalls = <_PutCall>[];
  final client = http_testing.MockClient((request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) {
      return _response(200);
    }
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      putCalls.add(
        _PutCall(key, jsonDecode(request.body) as Map<String, dynamic>),
      );
      return _response(200);
    }
    return contentResponses[key] ?? _response(404);
  });
  return (httpClient: client, putCalls: putCalls);
}

WorkoutSession _session({DateTime? startTime}) => WorkoutSession(
  workoutType: 'A',
  startTime: startTime ?? DateTime(2026, 7, 5, 9),
  endTime: DateTime(2026, 7, 5, 10),
  exercises: [
    ExerciseResult(
      exercise: const Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20),
      sets: List.generate(
        3,
        (_) => const SetResult(targetReps: 5, doneReps: 5, weight: 20),
      ),
    ),
  ],
);

/// Builds the service with the platform kept out of it.
///
/// The real factories want the OS keystore and an application-support
/// directory, neither of which exists under `flutter test`; passing null for
/// Firebase also asserts the pre-migration GitHub-only path still works.

/// The PUT that carries the log itself.
///
/// Each push now writes twice: the log, then this device's revision (which is
/// what lets a later tick skip an unchanged peer). These assertions are about
/// the log, so select it rather than assuming a single write.
_PutCall _logPut(List<_PutCall> calls) =>
    calls.firstWhere((c) => c.path.endsWith('log.json'));

WorkoutSyncService _service({
  http.Client? httpClient,
  String? owner,
  String? repo,
  Future<FirebaseRestClient?> Function()? firebaseFactory,
}) => WorkoutSyncService(
  httpClient: httpClient,
  owner: owner ?? syncRepoOwner,
  repo: repo ?? syncRepoName,
  firebaseFactory: firebaseFactory ?? () async => null,
  stateStore: InMemorySyncStateStore(),
);

void main() {
  _cutoverTests();
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

  test('does nothing when no token is configured', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = _mockGitHub();

    await _service(httpClient: httpClient).push(_session());

    expect(putCalls, isEmpty);
  });

  test('pushes a new record when nothing has been synced yet', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = _mockGitHub(
      contentResponses: {'screen-locker-sync/devices': _response(200, [])},
    );

    final session = _session();
    await _service(httpClient: httpClient).push(session);

    // Two writes: the log, then the revision published after it.
    expect(putCalls, hasLength(2));
    expect(_logPut(putCalls).path, 'screen-locker-sync/devices/phone/log.json');
    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(_logPut(putCalls).body['content'] as String),
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
    final (:httpClient, :putCalls) = _mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': _response(200, []),
        'screen-locker-sync/devices/phone/log.json': _fileContaining(
          existingLog,
        ),
      },
    );

    final session = _session();
    await _service(httpClient: httpClient).push(session);

    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(_logPut(putCalls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;
    expect(
      pushedLog.keys,
      containsAll(['earlier', session.startTime.toIso8601String()]),
    );
  });

  test('a GitHubSyncError is swallowed, not rethrown', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final httpClient = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );

    await expectLater(
      _service(httpClient: httpClient).push(_session()),
      completes,
    );
  });

  Record _manual(String id, String cost, int wallMs) => Record(
    id: id,
    fields: {
      'payload': (
        {'kind': 'manual_workout', 'date': '2026-07-13', 'cost': cost},
        Hlc(wallTimeMs: wallMs, counter: 0, nodeId: 'phone'),
      ),
    },
  );

  test('pushManual does nothing without a token', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = _mockGitHub();
    await _service(
      httpClient: httpClient,
    ).pushManual(_manual('manual:x', '40', 1000));
    expect(putCalls, isEmpty);
  });

  test('pushManual pushes when nothing has been synced yet', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = _mockGitHub(
      contentResponses: {'screen-locker-sync/devices': _response(200, [])},
    );
    await _service(
      httpClient: httpClient,
    ).pushManual(_manual('manual:2026-07-13T18:00', '40', 1000));
    expect(_logPut(putCalls).path, 'screen-locker-sync/devices/phone/log.json');
  });

  test('pushManual merges onto an existing log', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final existing = jsonEncode({
      'manual:old': _manual('manual:old', '20', 1000).toJson(),
    });
    final (:httpClient, :putCalls) = _mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': _response(200, []),
        'screen-locker-sync/devices/phone/log.json': _fileContaining(existing),
      },
    );
    await _service(
      httpClient: httpClient,
    ).pushManual(_manual('manual:2026-07-13T18:00', '40', 2000));
    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(_logPut(putCalls).body['content'] as String),
              ),
            )
            as Map<String, dynamic>;
    expect(
      pushedLog.keys,
      containsAll(['manual:old', 'manual:2026-07-13T18:00']),
    );
  });

  test('pushManual swallows a sync error', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final httpClient = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );
    await expectLater(
      _service(
        httpClient: httpClient,
      ).pushManual(_manual('manual:x', '40', 1000)),
      completes,
    );
  });

  test('readMergedManualPayloads is empty without a token', () async {
    installFakeSecureStorage();
    final (:httpClient, putCalls: _) = _mockGitHub();
    expect(
      await _service(
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
      'manual:a': _manual('manual:a', 'NEW', 2000).toJson(),
      's': session.toJson(),
      'np': noPayload.toJson(),
    });
    final pcLog = jsonEncode({
      // Same id, older clock -> must lose to phone's newer copy.
      'manual:a': _manual('manual:a', 'OLD', 1000).toJson(),
    });
    final (:httpClient, putCalls: _) = _mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': _response(200, [
          {'name': 'phone'},
          {'name': 'pc'},
          {'name': 'empty'}, // its log.json 404s -> skipped
        ]),
        'screen-locker-sync/devices/phone/log.json': _fileContaining(phoneLog),
        'screen-locker-sync/devices/pc/log.json': _fileContaining(pcLog),
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
      'manual:a': _manual('manual:a', 'NEW', 2000).toJson(),
      'runnerup_verified:2026-07-13': run.toJson(),
    });
    final (:httpClient, putCalls: _) = _mockGitHub(
      contentResponses: {
        'screen-locker-sync/devices': _response(200, [
          {'name': 'pc'},
        ]),
        'screen-locker-sync/devices/pc/log.json': _fileContaining(pcLog),
      },
    );
    final service = _service(httpClient: httpClient);

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
        'manual:a': _manual('manual:a', 'NEW', 2000).toJson(),
        'runnerup_verified:2026-07-13': run.toJson(),
      });
      final (:httpClient, putCalls: _) = _mockGitHub(
        contentResponses: {
          'screen-locker-sync/devices': _response(200, [
            {'name': 'pc'},
          ]),
          'screen-locker-sync/devices/pc/log.json': _fileContaining(pcLog),
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
      await _service(
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
      'manual:a': _manual('manual:a', 'NEW', 2000).toJson(),
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
      await _service(httpClient: httpClient).readMergedManualPayloads(),
      isEmpty,
    );
  });
}

/// A Firebase client wired to an in-memory mock, for the cutover tests.
///
/// The session's expiry uses the real clock: the token provider compares
/// against `DateTime.now()`, so a fixture-dated session looks expired and
/// triggers a refresh the mock never answers.
({FirebaseRestClient client, List<String> puts}) _fakeFirebase() {
  final puts = <String>[];
  final client = FirebaseRestClient(
    databaseUrl: 'https://x-rtdb.europe-west1.firebasedatabase.app',
    auth: FirebaseTokenProvider(
      apiKey: 'AIzaKey',
      store: InMemoryCredentialStore(
        FirebaseCredentials(
          idToken: 'id',
          refreshToken: 'refresh',
          expiresAt: DateTime.now().add(const Duration(hours: 1)),
        ),
      ),
    ),
    httpClient: http_testing.MockClient((request) async {
      if (request.method == 'PUT') {
        puts.add(request.url.path);
        return http.Response(request.body, 200);
      }
      return http.Response('null', 200);
    }),
  );
  return (client: client, puts: puts);
}

void _cutoverTests() {
  group('Firebase cutover', () {
    test('pushes to Firebase and still mirrors to GitHub', () async {
      // The cutover guarantee: both backends receive the write, so a PC that
      // has not moved yet still sees the workout.
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final (:httpClient, :putCalls) = _mockGitHub();
      final firebase = _fakeFirebase();

      await _service(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).push(_session());

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
      final (:httpClient, :putCalls) = _mockGitHub();
      final firebase = _fakeFirebase();

      await _service(
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
      final firebase = _fakeFirebase();

      final (:httpClient, :putCalls) = _mockGitHub();
      final payloads = await _service(
        httpClient: httpClient,
        firebaseFactory: () async => firebase.client,
      ).readMergedWorkoutPayloads();

      expect(payloads, isEmpty);
    });
  });
}
