/// Result of a single set during a workout session.
library;

class SetResult {
  const SetResult({
    required this.targetReps,
    required this.doneReps,
    required this.weight,
  });

  final int targetReps;

  /// How many reps the user actually completed (may be < targetReps on failure).
  final int doneReps;

  final double weight;

  /// True when the user completed every target rep.
  bool get succeeded => doneReps >= targetReps;

  SetResult copyWith({int? doneReps}) => SetResult(
        targetReps: targetReps,
        doneReps: doneReps ?? this.doneReps,
        weight: weight,
      );

  Map<String, dynamic> toJson() => {
        'targetReps': targetReps,
        'doneReps': doneReps,
        'weight': weight,
        'succeeded': succeeded,
      };

  factory SetResult.fromJson(Map<String, dynamic> json) => SetResult(
        targetReps: json['targetReps'] as int,
        doneReps: json['doneReps'] as int,
        weight: (json['weight'] as num).toDouble(),
      );
}
