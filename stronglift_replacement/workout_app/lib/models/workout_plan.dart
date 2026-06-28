/// Static workout plans A and B with their default exercise configurations.
library;

import 'package:workout_app/models/exercise.dart';

/// Situp has a lower max weight cap.
const double kSitupMaxWeight = 10;

/// Plan A: lower-body and push/pull focus.
final workoutA = [
  const Exercise(name: 'Dumbbell Lunge', sets: 5, reps: 12, weight: 7.5),
  const Exercise(
    name: 'Dumbbell Bench Press',
    sets: 5,
    reps: 12,
    weight: 22.5,
  ),
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
  const Exercise(
    name: 'Dumbbell Bench Press',
    sets: 5,
    reps: 12,
    weight: 22.5,
  ),
  const Exercise(
    name: 'Situp',
    sets: 3,
    reps: 30,
    weight: 10,
    maxWeight: kSitupMaxWeight,
    hasWarmup: false,
  ),
];
