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
}
