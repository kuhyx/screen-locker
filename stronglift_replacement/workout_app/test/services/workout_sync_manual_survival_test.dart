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

// Regression tests for the one thing that went RIGHT on 2026-08-15.
//
// A manual workout was logged while the phone was disconnected. When
// Firebase later connected, the entry was NOT erased -- the user called this
// out as good behaviour worth keeping. It is currently correct by
// construction (`MirrorStore.getFileText` falls through to the GitHub mirror
// when the Firebase primary returns null, so a first connect reads the prior
// log rather than an empty one), which is exactly why it needs pinning:
// nothing else would fail if that fall-through were removed.
void main() {
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

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
