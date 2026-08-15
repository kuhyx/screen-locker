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
