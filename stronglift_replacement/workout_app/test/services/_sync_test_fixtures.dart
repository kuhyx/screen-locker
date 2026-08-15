// Shared fixtures for the workout-sync test files.
//
// A sibling library rather than a `part`, so each split test file imports what
// it needs. The helpers live here because they are used across
// workout_sync_service_test.dart, workout_sync_cutover_test.dart and
// workout_sync_manual_survival_test.dart -- duplicating them would let the
// three drift apart silently.
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

http.Response syncResponse(int statusCode, [Object? jsonBody]) =>
    http.Response(jsonEncode(jsonBody ?? {}), statusCode);

http.Response fileContaining(String text) =>
    syncResponse(200, {'content': base64.encode(utf8.encode(text))});

class PutCall {
  PutCall(this.path, this.body);
  final String path;
  final Map<String, dynamic> body;
}

/// Builds a mock HTTP client backed by an in-memory router, matching
/// `crdt_sync_dart`'s own `sync_test.dart` helper: GET
/// `.../contents/<key>` returns [contentResponses]`[key]` (404 if absent),
/// the bare repo-existence GET always succeeds, and every PUT is recorded.
({http.Client httpClient, List<PutCall> putCalls}) mockGitHub({
  Map<String, http.Response> contentResponses = const {},
}) {
  final putCalls = <PutCall>[];
  final client = http_testing.MockClient((request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) {
      return syncResponse(200);
    }
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      putCalls.add(
        PutCall(key, jsonDecode(request.body) as Map<String, dynamic>),
      );
      return syncResponse(200);
    }
    return contentResponses[key] ?? syncResponse(404);
  });
  return (httpClient: client, putCalls: putCalls);
}

WorkoutSession workoutSession({DateTime? startTime}) => WorkoutSession(
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
PutCall logPut(List<PutCall> calls) =>
    calls.firstWhere((c) => c.path.endsWith('log.json'));

WorkoutSyncService syncService({
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

/// A Firebase client wired to an in-memory mock, for the cutover tests.
///
/// The session's expiry uses the real clock: the token provider compares
/// against `DateTime.now()`, so a fixture-dated session looks expired and
/// triggers a refresh the mock never answers.
({FirebaseRestClient client, List<String> puts}) fakeFirebase() {
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

/// A manual-workout [Record] as the phone writes it.
///
/// [wallMs] drives the HLC, so two calls with the same [id] and different
/// [wallMs] model the same entry edited on two devices.
Record manualRecord(String id, String cost, int wallMs) => Record(
  id: id,
  fields: {
    'payload': (
      {'kind': 'manual_workout', 'date': '2026-07-13', 'cost': cost},
      Hlc(wallTimeMs: wallMs, counter: 0, nodeId: 'phone'),
    ),
  },
);
