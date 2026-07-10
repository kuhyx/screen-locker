import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
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

void main() {
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

  test('does nothing when no token is configured', () async {
    installFakeSecureStorage();
    final (:httpClient, :putCalls) = _mockGitHub();

    await WorkoutSyncService(httpClient: httpClient).push(_session());

    expect(putCalls, isEmpty);
  });

  test('pushes a new record when nothing has been synced yet', () async {
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    final (:httpClient, :putCalls) = _mockGitHub(
      contentResponses: {'screen-locker-sync/devices': _response(200, [])},
    );

    final session = _session();
    await WorkoutSyncService(httpClient: httpClient).push(session);

    expect(putCalls, hasLength(1));
    expect(putCalls.single.path, 'screen-locker-sync/devices/phone/log.json');
    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(putCalls.single.body['content'] as String),
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
    await WorkoutSyncService(httpClient: httpClient).push(session);

    final pushedLog =
        jsonDecode(
              utf8.decode(
                base64.decode(putCalls.single.body['content'] as String),
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
      WorkoutSyncService(httpClient: httpClient).push(_session()),
      completes,
    );
  });
}
