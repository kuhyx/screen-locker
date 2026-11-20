import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/gap_deload.dart';
import 'package:workout_app/models/manual_deload.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

final _now = DateTime(2026, 11, 20, 18);

/// Saves a finished session of [names] that ended [daysAgo] days before
/// [_now], at the given target.
Future<void> _session(
  List<String> names, {
  required int daysAgo,
  double weight = 25,
  int reps = 5,
  bool succeeded = true,
}) async {
  final end = _now.subtract(Duration(days: daysAgo));
  final start = end.subtract(const Duration(hours: 1));
  await _svc.saveSession(
    date: start.toIso8601String().substring(0, 10),
    workoutType: 'A',
    durationSeconds: 3600,
    succeeded: succeeded,
    json: jsonEncode({
      'date': start.toIso8601String().substring(0, 10),
      'start_time': start.toIso8601String(),
      'end_time': end.toIso8601String(),
      'exercises': [
        for (final n in names)
          {
            'name': n,
            'targetWeight': weight,
            'targetReps': reps,
            'succeeded': succeeded,
          },
      ],
    }),
  );
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  final lift = workoutA.first.name;

  Future<void> at(double w) => _svc.setExerciseWeight(lift, w);

  group('applyGapDeloads', () {
    test('8-day gap: one step down, streaks zeroed, stamped, logged', () async {
      await at(25);
      await _session([lift], daysAgo: 8);
      final done = await _svc.applyGapDeloads(now: _now);
      expect(done.map((d) => d.name), [lift]);
      final s = (await _svc.getExerciseState(lift))!;
      expect(s.weight, 22.5);
      expect((s.successStreak, s.failStreak), (0, 0));
      expect(s.lastDeloadedAt, _now);
      final events = await _svc.getProgressionEvents(exercise: lift);
      expect(events.single.kind, kGapDeloadKind);
      expect((events.single.fromWeight, events.single.toWeight), (25.0, 22.5));
    });

    test('15-day gap: two steps', () async {
      await at(25);
      await _session([lift], daysAgo: 15);
      await _svc.applyGapDeloads(now: _now);
      expect((await _svc.getExerciseState(lift))!.weight, 20);
    });

    test('5-day gap: untouched', () async {
      await at(25);
      await _session([lift], daysAgo: 5);
      expect(await _svc.applyGapDeloads(now: _now), isEmpty);
      expect((await _svc.getExerciseState(lift))!.weight, 25);
    });

    test('never trained: no gap, no cut', () async {
      expect(await _svc.applyGapDeloads(now: _now), isEmpty);
    });

    test('reopening never cuts twice', () async {
      await at(25);
      await _session([lift], daysAgo: 8);
      await _svc.applyGapDeloads(now: _now);
      final later = _now.add(const Duration(minutes: 5));
      expect(await _svc.applyGapDeloads(now: later), isEmpty);
      // Not even a week later with no session in between.
      expect(
        await _svc.applyGapDeloads(now: _now.add(const Duration(days: 7))),
        isEmpty,
      );
      expect((await _svc.getExerciseState(lift))!.weight, 22.5);
    });

    test('a manual deload since the last session skips the auto cut', () async {
      await at(25);
      await _session([lift], daysAgo: 8);
      final m = await _svc.manualDeload(lift, source: DeloadSource.settings);
      expect(m.state!.lastDeloadedAt, isNotNull);
      expect(await _svc.applyGapDeloads(now: _now), isEmpty);
      expect((await _svc.getExerciseState(lift))!.weight, 22.5);
    });

    test('a session after a deload makes the next gap due again', () async {
      await at(25);
      await _session([lift], daysAgo: 30);
      await _svc.applyGapDeloads(now: _now.subtract(const Duration(days: 20)));
      await _session([lift], daysAgo: 9, weight: 20);
      final done = await _svc.applyGapDeloads(now: _now);
      expect(done, hasLength(1));
    });

    test('reps mode: two steps on reps', () async {
      final s = (await _svc.getExerciseState(lift))!;
      await _svc.setExerciseSettings(s.copyWith(mode: ProgressionMode.reps));
      await _svc.setExerciseReps(lift, 10);
      await _session([lift], daysAgo: 14);
      await _svc.applyGapDeloads(now: _now);
      expect((await _svc.getExerciseState(lift))!.reps, 8);
    });

    test('activeGapDeloads: shown until the next session', () async {
      await at(25);
      await _session([lift], daysAgo: 8);
      await _svc.applyGapDeloads(now: _now);
      final shown = await _svc.activeGapDeloads();
      expect(shown[lift]!.fromWeight, 25);
      await _session([lift], daysAgo: 0, weight: 22.5);
      expect(await _svc.activeGapDeloads(), isEmpty);
    });
  });

  group('runGapDeloadBackfill', () {
    test('exports before cutting, cuts stale lifts, never twice', () async {
      final fresh = workoutA[1].name;
      await at(25);
      await _svc.setExerciseWeight(fresh, 40);
      // kuhy's case: 7-day break, failed at the same weight, then 15 days.
      await _session([lift], daysAgo: 30);
      await _session([lift], daysAgo: 22, succeeded: false);
      await _session([lift], daysAgo: 16, succeeded: false);
      await _session([fresh], daysAgo: 2, weight: 40);

      final exports = <String>[];
      final r = await _svc.runGapDeloadBackfill(
        now: _now,
        writeExport: (json) async {
          // The export must hold the PRE-cut weights.
          final rows = (jsonDecode(json) as Map)['exercise_state'] as List;
          expect(
            rows.firstWhere((r) => r['name'] == lift)['weight'],
            25,
          );
          exports.add(json);
        },
      );
      expect(r.ran, isTrue);
      expect(exports, hasLength(1));
      // Gap now: 16 days = 2 steps; owed from the 8-day gap = 1 step.
      expect((await _svc.getExerciseState(lift))!.weight, 17.5);
      expect((await _svc.getExerciseState(fresh))!.weight, 40);
      final ev = await _svc.getProgressionEvents(exercise: lift);
      expect(ev.single.kind, kBackfillDeloadKind);

      final again = await _svc.runGapDeloadBackfill(
        now: _now,
        writeExport: (json) async => exports.add(json),
      );
      expect(again.ran, isFalse);
      expect(exports, hasLength(1));
      expect((await _svc.getExerciseState(lift))!.weight, 17.5);
    });

    test('a failed export cuts nothing and leaves the stamp unset', () async {
      await at(25);
      await _session([lift], daysAgo: 15);
      final r = await _svc.runGapDeloadBackfill(
        now: _now,
        writeExport: (_) async => throw const FileSystemExceptionLike(),
      );
      expect(r.ran, isFalse);
      expect((await _svc.getExerciseState(lift))!.weight, 25);
      final retry = await _svc.runGapDeloadBackfill(
        now: _now,
        writeExport: (_) async {},
      );
      expect(retry.ran, isTrue);
    });

    test('never raises a weight', () async {
      await at(5);
      await _session([lift], daysAgo: 40, weight: 5);
      await _svc.runGapDeloadBackfill(now: _now, writeExport: (_) async {});
      expect((await _svc.getExerciseState(lift))!.weight, 5);
    });
  });

  group('sandbox seed', () {
    test('seeds every gap case for the next workout load', () async {
      await _svc.seedGapScenarios(_now);
      expect(await _svc.getNextWorkoutType(), 'A');
      final done = {
        for (final d in await _svc.applyGapDeloads(now: _now)) d.name: d.to,
      };
      expect(done['Dumbbell Lunge']!.weight, 17.5);
      expect(done['Dumbbell Bench Press']!.weight, 17.5);
      expect(done.containsKey('Dumbbell Row'), isFalse);
      expect(done['Dumbbell Curl']!.weight, 7.5);
      expect(done['Dumbbell Romanian Deadlift']!.reps, 8);
      expect(done['Dumbbell Overhead Press']!.reps, 6);
    });
  });

  group('finish no longer deloads', () {
    test('a session after a long break progresses normally', () async {
      await at(22.5);
      await _session([lift], daysAgo: 0, weight: 22.5);
      await _svc.applyProgression(succeededExercises: {lift: true});
      expect((await _svc.getExerciseState(lift))!.weight, 22.5);
      expect((await _svc.getExerciseState(lift))!.successStreak, 1);
    });
  });
}

/// A stand-in I/O failure for the export writer.
class FileSystemExceptionLike implements Exception {
  /// Creates one.
  const FileSystemExceptionLike();
}
