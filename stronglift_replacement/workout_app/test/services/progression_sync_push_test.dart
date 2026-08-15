// pushProgression, the active-session publish, and the result type.
//
// Split out of progression_sync_service_test.dart, which keeps paths + pull.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';

import '_progression_test_fixtures.dart';

void main() {
  late FakeStore store;
  late ProgressionSyncService sync;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    store = FakeStore();
    sync = ProgressionSyncService(firebaseFactory: () async => store);
    StorageService.resetForTesting();
    await StorageService.init();
  });

  group('pushProgression', () {
    test('writes every exercise from a real install', () async {
      await markSynced();
      final result = await sync.pushProgression();

      expect(result.changed, isTrue);
      expect(result.count, 7);
      expect(store.files.keys, contains(endsWith('/Situp')));
    });

    test(
      'a fresh install writes NOTHING when Firebase already holds progression',
      () async {
        // The clobber guard. Evaluated once, before any write: a per-exercise
        // check still leaks factory defaults for every exercise Firebase
        // happens not to hold yet -- exactly the ones with no copy to lose.
        seedRemote(store, 'Dumbbell Bench Press', weight: 20);
        final before = Map<String, String>.from(store.files);

        final result = await sync.pushProgression();

        expect(result.changed, isFalse);
        expect(result.reason, contains('never pulled from Firebase'));
        expect(store.writes, 0, reason: 'not one write, not even a partial');
        expect(store.files, before);
        expect(
          store.files.containsKey(
            ProgressionSyncService.pathForExercise('Dumbbell Lunge'),
          ),
          isFalse,
          reason: 'an un-backed exercise must not gain a default record',
        );
      },
    );

    test(
      'finishing a workout on a never-pulled install cannot clobber remote',
      () async {
        // The exact production sequence that made the old guard useless:
        // _finishWorkout writes a workout_history row AND last_workout_type
        // BEFORE it pushes, so looksFreshlyInstalled() was already false by
        // the time the guard ran and factory defaults went up regardless.
        // Reachable without a fresh install too: connect Firebase late (the
        // uninstall wipes the keystore, so startup's pull found no account).
        seedRemote(store, 'Dumbbell Bench Press', weight: 60);
        await StorageService.instance.saveSession(
          date: '2026-08-10',
          workoutType: 'A',
          durationSeconds: 60,
          succeeded: true,
          json: '{}',
        );
        await StorageService.instance.setLastWorkoutType('A');
        expect(
          await StorageService.instance.looksFreshlyInstalled(),
          isFalse,
          reason: 'this is why the freshness test could not protect anything',
        );

        final result = await sync.pushProgression();

        expect(result.changed, isFalse);
        expect(store.writes, 0);
        expect(
          store.files[ProgressionSyncService.pathForExercise(
            'Dumbbell Bench Press',
          )],
          contains('60'),
          reason: 'the real remote progression is untouched',
        );
      },
    );

    test('a fresh install with an empty backend still seeds it', () async {
      final result = await sync.pushProgression();
      expect(result.changed, isTrue, reason: 'nothing to clobber');
    });

    test('a deliberate reset still reaches Firebase', () async {
      // resetExerciseToDefaults leaves reps and max_weight alone, so resetting
      // an exercise already at its default reps produces a row identical to a
      // seeded one. A value-based guard would refuse to push it and then
      // revert it on the next launch.
      seedRemote(store, 'Dumbbell Bench Press', weight: 20);
      await markSynced();
      await StorageService.instance.resetExerciseToDefaults(
        'Dumbbell Bench Press',
      );

      final result = await sync.pushProgression();

      expect(result.changed, isTrue);
      expect(
        store.files[ProgressionSyncService.pathForExercise(
          'Dumbbell Bench Press',
        )],
        contains('22.5'),
      );
    });

    test('stamps chain causally per record', () async {
      await markSynced();
      await sync.pushProgression();
      final first = hlcAt(store, 'Situp');
      await sync.pushProgression();
      final second = hlcAt(store, 'Situp');

      expect(first < second, isTrue);
    });

    test('says why when no Firebase account is configured', () async {
      final offline = ProgressionSyncService(firebaseFactory: () async => null);
      final result = await offline.pushProgression();
      expect(result.changed, isFalse);
      expect(result.reason, contains('no Firebase account'));
    });

    test('reports a backend failure instead of swallowing it', () async {
      await markSynced();
      store.throwOnGet = FirebaseSyncError('rtdb exploded');
      final result = await sync.pushProgression();
      expect(result.changed, isFalse);
      expect(result.reason, contains('push failed'));
    });
  });

  group('active session', () {
    test('round-trips through Firebase', () async {
      expect(await sync.readActiveSession(), isNull);

      await sync.pushActiveSession({'workoutType': 'B', 'startTimeMs': 123});

      final read = await sync.readActiveSession();
      expect(read!['workoutType'], 'B');
    });

    test('clearing it cannot resurrect a finished workout', () async {
      await sync.pushActiveSession({'workoutType': 'A'});
      final result = await sync.pushActiveSession(null);

      expect(result.changed, isTrue);
      expect(result.reason, contains('cleared'));
      expect(await sync.readActiveSession(), isNull);
    });

    test('says why when no Firebase account is configured', () async {
      final offline = ProgressionSyncService(firebaseFactory: () async => null);
      final result = await offline.pushActiveSession({'a': 1});
      expect(result.changed, isFalse);
      expect(result.reason, contains('no Firebase account'));
      expect(await offline.readActiveSession(), isNull);
    });

    test('reports a push failure instead of swallowing it', () async {
      store.throwOnGet = FirebaseSyncError('rtdb exploded');
      final result = await sync.pushActiveSession({'a': 1});
      // The write path does not read first, so this one succeeds; the read
      // path is what surfaces the error.
      expect(result.changed, isTrue);
      expect(await sync.readActiveSession(), isNull);
    });

    test('a failed write is reported, not swallowed', () async {
      final result = await ProgressionSyncService(
        firebaseFactory: () async => ExplodingStore(),
      ).pushActiveSession({'a': 1});

      expect(result.changed, isFalse);
      expect(result.reason, contains('active session push failed'));
    });
  });

  test('ProgressionSyncResult prints its fields for debugging', () {
    const result = ProgressionSyncResult(
      changed: true,
      count: 3,
      reason: 'pushed',
    );
    expect(
      result.toString(),
      'ProgressionSyncResult(changed: true, count: 3, reason: pushed)',
    );
  });
}
