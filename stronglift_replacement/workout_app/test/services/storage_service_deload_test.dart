import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';

import '_deload_test_fixtures.dart';

StorageService get _svc => StorageService.instance;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late Directory backupDir;

  setUp(() async {
    // Deloads trigger a fire-and-forget backup: keep it off /sdcard.
    backupDir = await Directory.systemTemp.createTemp('deload_backup');
    BackupService.baseDir = backupDir.path;
    StorageService.resetForTesting();
    await StorageService.init();
  });

  tearDown(() async {
    BackupService.baseDir = kBackupDir;
    await backupDir.delete(recursive: true);
  });

  Future<void> seed(String name, {required double weight}) =>
      _svc.replaceExerciseState(deloadState(name: name, weight: weight));

  group('manualDeload steps down exactly like a fail streak', () {
    test('weight mode: 100 kg becomes 97.5 kg, reps unchanged', () async {
      await _svc.replaceExerciseState(deloadState());
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.settings,
      );
      expect(r.applied, isTrue);
      expect((r.state!.weight, r.state!.reps), (97.5, 5));
      expect(r.reason, 'Deload Lift: 100 kg × 5 → 97.5 kg × 5');
      final stored = (await _svc.getExerciseState('Deload Lift'))!;
      expect((stored.weight, stored.reps), (97.5, 5));
    });

    test('reps mode: one rep fewer, weight untouched', () async {
      await _svc.replaceExerciseState(
        deloadState(mode: ProgressionMode.reps, reps: 20),
      );
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.workout,
      );
      expect((r.state!.weight, r.state!.reps), (100.0, 19));
      expect((await _svc.getExerciseState('Deload Lift'))!.reps, 19);
    });

    test('double progression above repsLow drops one rep', () async {
      await _svc.replaceExerciseState(
        deloadState(mode: ProgressionMode.doubleProgression, reps: 9),
      );
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.workout,
      );
      expect((r.state!.weight, r.state!.reps), (100.0, 8));
    });

    test(
      'double progression at repsLow goes lighter and to repsHigh',
      () async {
        await _svc.replaceExerciseState(
          deloadState(mode: ProgressionMode.doubleProgression, reps: 6),
        );
        final r = await _svc.manualDeload(
          'Deload Lift',
          source: DeloadSource.workout,
        );
        expect((r.state!.weight, r.state!.reps), (97.5, 12));
        final stored = (await _svc.getExerciseState('Deload Lift'))!;
        expect((stored.weight, stored.reps), (97.5, 12));
      },
    );

    test('clears both streaks, in the result and in the database', () async {
      await _svc.replaceExerciseState(deloadState());
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.settings,
      );
      expect((r.state!.successStreak, r.state!.failStreak), (0, 0));
      final stored = (await _svc.getExerciseState('Deload Lift'))!;
      expect((stored.successStreak, stored.failStreak), (0, 0));
    });

    test('renders non-integer weights without a trailing .0', () async {
      await _svc.replaceExerciseState(deloadState(weight: 22.5));
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.settings,
      );
      expect(r.reason, 'Deload Lift: 22.5 kg × 5 → 20 kg × 5');
    });
  });

  group('manualDeload refusals change nothing', () {
    test('unknown exercise: null state, reason, no event', () async {
      final r = await _svc.manualDeload(
        'Nonexistent',
        source: DeloadSource.settings,
      );
      expect(r.applied, isFalse);
      expect(r.state, isNull);
      expect(r.reason, contains('No saved state for "Nonexistent"'));
      expect(await _svc.getProgressionEvents(), isEmpty);
    });

    test('weight mode at 0 kg has nowhere lower to go', () async {
      await _svc.replaceExerciseState(deloadState(weight: 0));
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.workout,
      );
      expect(r.applied, isFalse);
      expect(r.reason, contains('already at 0 kg × 5'));
      expect(r.reason, contains('weight progression'));
      final stored = (await _svc.getExerciseState('Deload Lift'))!;
      expect((stored.weight, stored.reps), (0.0, 5));
      // Refusal must not wipe the streaks either.
      expect((stored.successStreak, stored.failStreak), (2, 1));
      expect(await _svc.getProgressionEvents(), isEmpty);
    });

    test('reps mode at 1 rep is the floor', () async {
      await _svc.replaceExerciseState(
        deloadState(mode: ProgressionMode.reps, reps: 1),
      );
      final r = await _svc.manualDeload(
        'Deload Lift',
        source: DeloadSource.workout,
      );
      expect(r.applied, isFalse);
      expect(r.reason, contains('reps progression'));
      expect(await _svc.getProgressionEvents(), isEmpty);
    });
  });

  group('progression_events', () {
    test('a deload writes one fully populated row', () async {
      await _svc.replaceExerciseState(deloadState());
      final before = DateTime.now();
      await _svc.manualDeload('Deload Lift', source: DeloadSource.workout);
      final after = DateTime.now();

      final events = await _svc.getProgressionEvents();
      expect(events, hasLength(1));
      final e = events.single;
      expect(e.exercise, 'Deload Lift');
      expect(e.kind, kManualDeloadKind);
      expect(e.kind, 'manual_deload');
      expect(e.source, 'workout');
      expect((e.fromWeight, e.fromReps), (100.0, 5));
      expect((e.toWeight, e.toReps), (97.5, 5));
      expect(e.at.isBefore(before), isFalse);
      expect(e.at.isAfter(after), isFalse);
    });

    test('source is stored per call', () async {
      await seed('Deload Lift', weight: 100);
      await _svc.manualDeload('Deload Lift', source: DeloadSource.settings);
      expect((await _svc.getProgressionEvents()).single.source, 'settings');
    });

    test('newest first, filterable by exercise', () async {
      await seed('Lift One', weight: 100);
      await seed('Lift Two', weight: 50);
      await _svc.manualDeload('Lift One', source: DeloadSource.settings);
      await _svc.manualDeload('Lift Two', source: DeloadSource.settings);
      await _svc.manualDeload('Lift One', source: DeloadSource.workout);

      final all = await _svc.getProgressionEvents();
      expect(
        [for (final e in all) (e.exercise, e.toWeight)],
        [('Lift One', 95.0), ('Lift Two', 47.5), ('Lift One', 97.5)],
      );
      final one = await _svc.getProgressionEvents(exercise: 'Lift One');
      expect([for (final e in one) e.toWeight], [95.0, 97.5]);
      expect(await _svc.getProgressionEvents(exercise: 'Nobody'), isEmpty);
    });
  });
}
