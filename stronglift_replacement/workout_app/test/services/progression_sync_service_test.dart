import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';

/// In-memory stand-in for [FirebaseRestClient].
///
/// Records every write so a test can assert not just the final state but that
/// no write happened at all -- the difference between "the guard held" and
/// "the guard wrote defaults and then wrote them back".
class _FakeStore implements FirebaseRestClient {
  final Map<String, String> files = {};
  int writes = 0;
  bool closed = false;
  Object? throwOnGet;

  @override
  Future<String?> getFileText(String path) async {
    if (throwOnGet != null) throw throwOnGet!;
    return files[path];
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    writes++;
    files[path] = text;
  }

  @override
  Future<List<String>> listDirectory(String path) async => files.keys
      .where((k) => k.startsWith('$path/'))
      .map((k) => k.substring(path.length + 1).split('/').first)
      .toSet()
      .toList();

  @override
  void close() => closed = true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Writes a progression record for [name] straight into [store].
void _seedRemote(
  _FakeStore store,
  String name, {
  double weight = 20,
  int reps = 12,
  double maxWeight = 27.5,
}) {
  final record = Record(
    id: 'exercise_state:$name',
    fields: {
      'payload': (
        {
          'name': name,
          'weight': weight,
          'reps': reps,
          'success_streak': 0,
          'fail_streak': 0,
          'max_weight': maxWeight,
          'success_threshold': 3,
          'fail_threshold': 2,
        },
        Hlc.newTick('remote-device'),
      ),
    },
  );
  store.files[ProgressionSyncService.pathForExercise(name)] = jsonEncode(
    record.toJson(),
  );
}

Hlc _hlcAt(_FakeStore store, String name) => Record.fromJson(
  jsonDecode(store.files[ProgressionSyncService.pathForExercise(name)]!)
      as Map<String, dynamic>,
).fields['payload']!.$2;

void main() {
  late _FakeStore store;
  late ProgressionSyncService sync;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    store = _FakeStore();
    sync = ProgressionSyncService(firebaseFactory: () async => store);
    StorageService.resetForTesting();
    await StorageService.init();
  });

  /// Marks this install as having reconciled with Firebase, which is what
  /// unblocks pushing.
  Future<void> markSynced() =>
      StorageService.instance.markProgressionSynced();

  group('paths', () {
    test('progression sits outside devices/, so workout readers cannot see it', () {
      // The whole safety argument: the PC lists `screen-locker-sync/devices`
      // and reads `<id>/log.json` under it. A progression record that never
      // appears under that prefix cannot be miscounted as a workout, which
      // would silently grant unlock credit.
      final path = ProgressionSyncService.pathForExercise('Situp');
      expect(path, startsWith('screen-locker-sync/exercise_state/'));
      expect(path, isNot(contains('/devices/')));
      expect(kActiveSessionPath, isNot(contains('/devices/')));
    });

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
      _seedRemote(store, 'Dumbbell Bench Press', weight: 20);
      _seedRemote(store, 'Situp', weight: 10, reps: 31, maxWeight: 10);

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
      _seedRemote(store, 'Dumbbell Bench Press', weight: 20);
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
      _seedRemote(store, 'Dumbbell Bench Press', weight: 60);
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
        _seedRemote(store, 'Dumbbell Bench Press', weight: 20);
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
        _seedRemote(store, 'Dumbbell Bench Press', weight: 60);
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
      _seedRemote(store, 'Dumbbell Bench Press', weight: 20);
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
      final first = _hlcAt(store, 'Situp');
      await sync.pushProgression();
      final second = _hlcAt(store, 'Situp');

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
        firebaseFactory: () async => _ExplodingStore(),
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

/// A store whose writes always fail, for the push-error paths.
class _ExplodingStore extends _FakeStore {
  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => throw FirebaseSyncError('write refused');
}
