// The progression-mode, warmup, pause and rest fields on a Firebase progression
// record: pushed, pulled back, and read leniently from records written
// before they existed.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';

import '_progression_test_fixtures.dart';

Map<String, dynamic> _payload(FakeStore store, String name) =>
    Record.fromJson(
          jsonDecode(store.files[ProgressionSyncService.pathForExercise(name)]!)
              as Map<String, dynamic>,
        ).fields['payload']!.$1
        as Map<String, dynamic>;

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

  test(
    'a record from before modes existed restores with the defaults',
    () async {
      seedRemote(store, 'Situp', weight: 5, reps: 31, maxWeight: 10);
      seedRemote(store, 'Dumbbell Row', weight: 27.5, reps: 6);

      await sync.pullProgression();

      final situp = (await StorageService.instance.getExerciseState('Situp'))!;
      expect(situp.mode, ProgressionMode.weight);
      expect((situp.repsHigh, situp.repsLow), (12, 6));
      // Missing has_warmup = the plan's default, never a blanket "on".
      expect(situp.hasWarmup, isFalse);
      expect(situp.pausedUntil, isNull);
      expect(
        (situp.restSuccessSecs, situp.restFailSecs, situp.restWarmupSecs),
        (180, 300, 180),
      );
      final row = (await StorageService.instance.getExerciseState(
        'Dumbbell Row',
      ))!;
      expect(row.hasWarmup, isTrue);
    },
  );

  test(
    'mode, rep range, warmup, pause and rests survive a push and a pull',
    () async {
      final storage = StorageService.instance;
      final situp = (await storage.getExerciseState('Situp'))!;
      await storage.setExerciseSettings(
        situp.copyWith(
          mode: ProgressionMode.doubleProgression,
          repsHigh: 20,
          repsLow: 10,
          hasWarmup: true,
          pausedUntil: DateTime(2026, 10, 11),
          restSuccessSecs: 150,
          restFailSecs: 240,
          restWarmupSecs: 90,
        ),
      );
      await markSynced();
      await sync.pushProgression();

      final pushed = _payload(store, 'Situp');
      expect(pushed['progression_mode'], 'double');
      expect((pushed['reps_high'], pushed['reps_low']), (20, 10));
      expect(pushed['has_warmup'], isTrue);
      expect(pushed['paused_until'], '2026-10-11');
      expect(
        (
          pushed['rest_success_secs'],
          pushed['rest_fail_secs'],
          pushed['rest_warmup_secs'],
        ),
        (150, 240, 90),
      );
      expect(_payload(store, 'Dumbbell Row')['paused_until'], isNull);

      // A reinstall: fresh database, same Firebase.
      StorageService.resetForTesting();
      await StorageService.init();
      await sync.pullProgression();

      final back = (await StorageService.instance.getExerciseState('Situp'))!;
      expect(back.mode, ProgressionMode.doubleProgression);
      expect((back.repsHigh, back.repsLow), (20, 10));
      expect(back.hasWarmup, isTrue);
      expect(back.pausedUntil, DateTime(2026, 10, 11));
      expect(
        (back.restSuccessSecs, back.restFailSecs, back.restWarmupSecs),
        (150, 240, 90),
      );
    },
  );
}
