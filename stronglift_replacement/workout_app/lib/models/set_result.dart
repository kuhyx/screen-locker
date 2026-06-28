/// Result of a single set during a workout session.
library;

/// Immutable result of one set, recording target vs actual reps.
class SetResult {
  /// Creates a set result.
  const SetResult({
    required this.targetReps,
    required this.doneReps,
    required this.weight,
  });

  /// Deserializes a set result from a JSON map.
  factory SetResult.fromJson(Map<String, dynamic> json) => SetResult(
    targetReps: json['targetReps'] as int,
    doneReps: json['doneReps'] as int,
    weight: (json['weight'] as num).toDouble(),
  );

  /// Target number of reps for this set.
  final int targetReps;

  /// Reps actually completed (may be less than [targetReps] on failure).
  final int doneReps;

  /// Weight used for this set in kg.
  final double weight;

  /// True when the user completed every target rep.
  bool get succeeded => doneReps >= targetReps;

  /// Returns a copy with [doneReps] replaced.
  SetResult copyWith({int? doneReps}) => SetResult(
    targetReps: targetReps,
    doneReps: doneReps ?? this.doneReps,
    weight: weight,
  );

  /// Serializes this set result to a JSON map.
  Map<String, dynamic> toJson() => {
    'targetReps': targetReps,
    'doneReps': doneReps,
    'weight': weight,
    'succeeded': succeeded,
  };
}
