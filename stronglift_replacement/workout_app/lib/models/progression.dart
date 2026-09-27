/// The progression rule: what a success, a failure, or a long break does to
/// an exercise's target, for each of the three progression modes.
///
/// Pure on purpose. `applyProgression` (what finishing a workout does) and
/// the workout/history previews ("→ 25 kg × 6") both call these functions,
/// so a preview can never promise something the finish does not deliver.
library;

import 'dart:developer';

import 'package:workout_app/models/exercise.dart';

/// Default rep ceiling `n` for [ProgressionMode.doubleProgression].
const int kDefaultRepsHigh = 12;

/// Default restart reps `m` for [ProgressionMode.doubleProgression].
const int kDefaultRepsLow = 6;

/// How an exercise advances once its success streak hits the threshold.
enum ProgressionMode {
  /// +2.5 kg per step; +1 rep instead once the weight cap is reached.
  weight('weight'),

  /// +1 rep per step, weight never changes.
  reps('reps'),

  /// +1 rep per step until `n` reps, then +2.5 kg and back to `m` reps.
  doubleProgression('double');

  const ProgressionMode(this.storageKey);

  /// Value stored in SQLite and Firebase. Never rename: synced data holds it.
  final String storageKey;

  /// Parses [raw]; null means "not set yet" and is silently [weight] (every
  /// row written before modes existed). Anything else unknown is a bug in
  /// some writer, so it is reported before falling back.
  static ProgressionMode parse(Object? raw) {
    if (raw == null) return weight;
    for (final m in values) {
      if (m.storageKey == raw) return m;
    }
    log(
      'ProgressionMode: unknown mode "$raw" — treating it as weight '
      'progression. Some writer stored a value this build does not know.',
      level: 900,
    );
    return weight;
  }
}

/// A working target: the weight and reps of every working set.
class ProgressionTarget {
  /// Creates a [ProgressionTarget].
  const ProgressionTarget(this.weight, this.reps);

  /// Working weight in kg.
  final double weight;

  /// Target reps per set.
  final int reps;

  @override
  String toString() => 'ProgressionTarget($weight kg × $reps)';
}

/// The inputs the rule needs; implemented by `ExerciseState`.
abstract interface class ProgressionInputs {
  /// Current working weight in kg.
  double get weight;

  /// Current target reps.
  int get reps;

  /// Weight cap (the heaviest dumbbell available).
  double get maxWeight;

  /// The active progression mode.
  ProgressionMode get mode;

  /// Double progression: reps at which the weight goes up (`n`).
  int get repsHigh;

  /// Double progression: reps the heavier weight starts at (`m`).
  int get repsLow;
}

/// The target after a success streak reaches its threshold.
ProgressionTarget targetAfterSuccess(ProgressionInputs s) {
  final atCap = s.weight >= s.maxWeight;
  final heavier = (s.weight + kWeightIncrement).clamp(0.0, s.maxWeight);
  switch (s.mode) {
    case ProgressionMode.weight:
      return atCap
          ? ProgressionTarget(s.weight, s.reps + 1)
          : ProgressionTarget(heavier, s.reps);
    case ProgressionMode.reps:
      return ProgressionTarget(s.weight, s.reps + 1);
    case ProgressionMode.doubleProgression:
      // `>=`, not `==`: an exercise switched into this mode above `n` reps
      // (Situp sits at 30) must still promote, not climb forever.
      if (s.reps < s.repsHigh || atCap) {
        return ProgressionTarget(s.weight, s.reps + 1);
      }
      return ProgressionTarget(heavier, s.repsLow);
  }
}

/// The target after a fail streak reaches its threshold, or after a break
/// of more than a week (one regression step in every mode).
ProgressionTarget targetAfterFailure(ProgressionInputs s) {
  final lighter = (s.weight - kWeightIncrement).clamp(0.0, s.maxWeight);
  switch (s.mode) {
    case ProgressionMode.weight:
      return ProgressionTarget(lighter, s.reps);
    case ProgressionMode.reps:
      return ProgressionTarget(s.weight, s.reps - 1 < 1 ? 1 : s.reps - 1);
    case ProgressionMode.doubleProgression:
      if (s.reps > s.repsLow) return ProgressionTarget(s.weight, s.reps - 1);
      // At `m` the step down is the exact inverse of a step up: lighter and
      // back to `n`. With no weight left to drop that would only make the
      // exercise harder, so it stays put.
      if (s.weight <= 0) return ProgressionTarget(s.weight, s.reps);
      return ProgressionTarget(lighter, s.repsHigh);
  }
}

/// Short label for moving from [from] to [to]: `25 kg`, `13 reps`,
/// `25 kg × 6`, or `same` when the rule has nowhere left to go.
String describeTargetChange(ProgressionInputs from, ProgressionTarget to) {
  final weightChanged = to.weight != from.weight;
  final repsChanged = to.reps != from.reps;
  if (weightChanged && repsChanged) return '${_kg(to.weight)} kg × ${to.reps}';
  if (weightChanged) return '${_kg(to.weight)} kg';
  if (repsChanged) return '${to.reps} reps';
  return 'same';
}

/// `25` for 25.0, `27.5` for 27.5 — no trailing `.0` noise in tight rows.
String _kg(double w) =>
    w == w.roundToDouble() ? w.toInt().toString() : w.toString();
