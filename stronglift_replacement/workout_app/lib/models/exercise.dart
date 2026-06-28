/// Core domain model for a single exercise and its current progression state.
library;

/// Default weight cap: above this, reps increase instead of weight.
const double kDefaultMaxWeight = 27.5;

/// Weight increment used for progression steps (kg).
const double kWeightIncrement = 2.5;

/// Immutable definition of a single exercise and its current target state.
class Exercise {
  /// Creates an exercise with the given parameters.
  const Exercise({
    required this.name,
    required this.sets,
    required this.reps,
    required this.weight,
    this.maxWeight = kDefaultMaxWeight,
    this.hasWarmup = true,
  });

  /// Deserializes an exercise from a JSON map.
  factory Exercise.fromJson(Map<String, dynamic> json) => Exercise(
    name: json['name'] as String,
    sets: json['sets'] as int,
    reps: json['reps'] as int,
    weight: (json['weight'] as num).toDouble(),
    maxWeight: (json['maxWeight'] as num?)?.toDouble() ?? kDefaultMaxWeight,
    hasWarmup: json['hasWarmup'] as bool? ?? true,
  );

  /// Display name of the exercise.
  final String name;

  /// Number of working sets per session.
  final int sets;

  /// Target reps per set.
  final int reps;

  /// Current working weight in kg.
  final double weight;

  /// Weight cap beyond which reps increase instead of weight.
  final double maxWeight;

  /// Whether a warmup set should be shown for this exercise.
  final bool hasWarmup;

  /// Warmup weight: 4/5 of target weight, rounded DOWN to nearest 2.5 kg.
  double get warmupWeight {
    final raw = weight * 4.0 / 5.0;
    return (raw / kWeightIncrement).floor() * kWeightIncrement;
  }

  /// Returns a copy of this exercise with the given fields replaced.
  Exercise copyWith({
    String? name,
    int? sets,
    int? reps,
    double? weight,
    double? maxWeight,
    bool? hasWarmup,
  }) {
    return Exercise(
      name: name ?? this.name,
      sets: sets ?? this.sets,
      reps: reps ?? this.reps,
      weight: weight ?? this.weight,
      maxWeight: maxWeight ?? this.maxWeight,
      hasWarmup: hasWarmup ?? this.hasWarmup,
    );
  }

  /// Serializes this exercise to a JSON map.
  Map<String, dynamic> toJson() => {
    'name': name,
    'sets': sets,
    'reps': reps,
    'weight': weight,
    'maxWeight': maxWeight,
    'hasWarmup': hasWarmup,
  };
}
