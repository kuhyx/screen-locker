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

  group('paths', () {
    test(
      'progression sits outside devices/, so workout readers cannot see it',
      () {
        // The whole safety argument: the PC lists `screen-locker-sync/devices`
        // and reads `<id>/log.json` under it. A progression record that never
        // appears under that prefix cannot be miscounted as a workout, which
        // would silently grant unlock credit.
        final path = ProgressionSyncService.pathForExercise('Situp');
        expect(path, startsWith('screen-locker-sync/exercise_state/'));
        expect(path, isNot(contains('/devices/')));
        expect(kActiveSessionPath, isNot(contains('/devices/')));
      },
    );

    test('the exercise name is used raw, so the client can escape it once', () {
      // Double-encoding here would write to a different key than
      // listDirectory reports back.
      expect(
        ProgressionSyncService.pathForExercise('Dumbbell Bench Press'),
        endsWith('/Dumbbell Bench Press'),
      );
    });
  });

  group('pullProgression', () {
    test('restores every remote record into a fresh install', () async {
      seedRemote(store, 'Dumbbell Bench Press', weight: 20);
      seedRemote(store, 'Situp', weight: 10, reps: 31, maxWeight: 10);

      final result = await sync.pullProgression();

      expect(result.changed, isTrue);
      expect(result.count, 2);
      final bench = await StorageService.instance.getExerciseState(
        'Dumbbell Bench Press',
      );
      expect(bench!.weight, 20, reason: 'restored, not the factory 22.5');
      final situp = await StorageService.instance.getExerciseState('Situp');
      expect(situp!.reps, 31, reason: 'restored, not the factory 30');
    });

    test('declines once this install has reconciled with Firebase', () async {
      seedRemote(store, 'Dumbbell Bench Press', weight: 20);
      await markSynced();
      await StorageService.instance.setExerciseWeight(
        'Dumbbell Bench Press',
        42.5,
      );

      final result = await sync.pullProgression();

      expect(result.changed, isFalse);
      expect(result.reason, contains('already reconciled'));
      final bench = await StorageService.instance.getExerciseState(
        'Dumbbell Bench Press',
      );
      expect(bench!.weight, 42.5, reason: 'local progression survived');
    });

    test('a hand-edited weight is NOT reverted on the next launch', () async {
      // Regression: gating the pull on looksFreshlyInstalled() reverted this.
      // setExerciseWeight writes neither history nor last_workout_type, so the
      // DB still "looks fresh" afterwards and the next launch pulled the old
      // remote value back over the user's own edit.
      seedRemote(store, 'Dumbbell Bench Press', weight: 60);
      await sync.pullProgression(); // first launch reconciles
      await StorageService.instance.setExerciseWeight(
        'Dumbbell Bench Press',
        30,
      );

      await sync.pullProgression(); // next launch

      final bench = await StorageService.instance.getExerciseState(
        'Dumbbell Bench Press',
      );
      expect(bench!.weight, 30, reason: 'the user edit stands');
    });

    test('a successful pull unblocks this device for pushing', () async {
      expect(await StorageService.instance.hasSyncedProgression(), isFalse);
      await sync.pullProgression();
      expect(
        await StorageService.instance.hasSyncedProgression(),
        isTrue,
        reason: 'an empty backend is still a successful reconcile',
      );
    });

    test('a failed pull leaves this device blocked from pushing', () async {
      store.throwOnGet = FirebaseSyncError('rtdb exploded');
      await sync.pullProgression();
      expect(
        await StorageService.instance.hasSyncedProgression(),
        isFalse,
        reason: 'never reconciled, so a later push must not clobber',
      );
    });

    test('reports the empty case rather than claiming success', () async {
      final result = await sync.pullProgression();
      expect(result.changed, isFalse);
      expect(result.reason, contains('no exercise records'));
    });

    test('says why when no Firebase account is configured', () async {
      final offline = ProgressionSyncService(firebaseFactory: () async => null);
      final result = await offline.pullProgression();
      expect(result.changed, isFalse);
      expect(result.reason, contains('no Firebase account'));
    });

    test('reports a backend failure instead of swallowing it', () async {
      store.throwOnGet = FirebaseSyncError('rtdb exploded');
      final result = await sync.pullProgression();
      expect(result.changed, isFalse);
      expect(result.reason, contains('pull failed'));
      expect(store.closed, isTrue);
    });

    test('treats a corrupt remote record as absent', () async {
      store.files[ProgressionSyncService.pathForExercise('Situp')] =
          'not json at all';
      final result = await sync.pullProgression();
      expect(result.changed, isFalse);
    });
  });
}
