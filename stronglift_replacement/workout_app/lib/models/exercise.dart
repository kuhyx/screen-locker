/// Core domain model for a single exercise definition and its current progression state.
library;

const double kDefaultMaxWeight = 27.5;
const double kWeightIncrement = 2.5;

class Exercise {
  const Exercise({
    required this.name,
    required this.sets,
    required this.reps,
    required this.weight,
    this.maxWeight = kDefaultMaxWeight,
  });

  final String name;
  final int sets;
  final int reps;
  final double weight;

  /// Weight cap beyond which reps increase instead of weight.
  final double maxWeight;

  /// Warmup weight: 4/5 of target weight, rounded DOWN to nearest 2.5 kg.
  double get warmupWeight {
    final raw = weight * 4.0 / 5.0;
    return (raw / kWeightIncrement).floor() * kWeightIncrement;
  }

  Exercise copyWith({
    String? name,
    int? sets,
    int? reps,
    double? weight,
    double? maxWeight,
  }) {
    return Exercise(
      name: name ?? this.name,
      sets: sets ?? this.sets,
      reps: reps ?? this.reps,
      weight: weight ?? this.weight,
      maxWeight: maxWeight ?? this.maxWeight,
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'sets': sets,
        'reps': reps,
        'weight': weight,
        'maxWeight': maxWeight,
      };

  factory Exercise.fromJson(Map<String, dynamic> json) => Exercise(
        name: json['name'] as String,
        sets: json['sets'] as int,
        reps: json['reps'] as int,
        weight: (json['weight'] as num).toDouble(),
        maxWeight: (json['maxWeight'] as num?)?.toDouble() ?? kDefaultMaxWeight,
      );
}
