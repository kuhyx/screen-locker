/// Static workout plans A and B with their default exercise configurations.
library;

import 'package:workout_app/models/exercise.dart';

/// Situp has a lower max weight cap.
const double kSitupMaxWeight = 10;

/// Plan A: lower-body and push/pull focus.
final workoutA = [
  const Exercise(name: 'Dumbbell Lunge', sets: 5, reps: 12, weight: 7.5),
  const Exercise(name: 'Dumbbell Bench Press', sets: 5, reps: 12, weight: 22.5),
  const Exercise(name: 'Dumbbell Row', sets: 4, reps: 6, weight: 22.5),
  const Exercise(name: 'Dumbbell Curl', sets: 3, reps: 12, weight: 12.5),
];

/// Plan B: posterior chain, overhead, and core focus.
final workoutB = [
  const Exercise(
    name: 'Dumbbell Romanian Deadlift',
    sets: 5,
    reps: 7,
    weight: 27.5,
  ),
  const Exercise(
    name: 'Dumbbell Overhead Press',
    sets: 5,
    reps: 12,
    weight: 7.5,
  ),
  const Exercise(name: 'Dumbbell Bench Press', sets: 5, reps: 12, weight: 22.5),
  const Exercise(
    name: 'Situp',
    sets: 3,
    reps: 30,
    weight: 10,
    maxWeight: kSitupMaxWeight,
    hasWarmup: false,
  ),
];

/// The plan's own warmup default for [name]; true for an unknown name.
///
/// What a NULL `has_warmup` means. The column is nullable on purpose: rows
/// from before the toggle existed, old backups and old Firebase records all
/// lack it, and a blanket default of "on" would quietly give Situp its
/// warmup back on every restore.
bool planHasWarmup(String name) {
  for (final ex in [...workoutA, ...workoutB]) {
    if (ex.name == name) return ex.hasWarmup;
  }
  return true;
}
