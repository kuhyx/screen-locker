/// Card widget for a single exercise showing warmup and main-set rep circles.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/widgets/rep_circle.dart';

class ExerciseTile extends StatelessWidget {
  const ExerciseTile({
    super.key,
    required this.exercise,
    required this.tapped,
    required this.doneReps,
    required this.warmupTapped,
    required this.successThreshold,
    required this.failThreshold,
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
    required this.onThresholdChanged,
  });

  final Exercise exercise;
  final List<bool> tapped;
  final List<int> doneReps;
  final bool warmupTapped;
  final int successThreshold;
  final int failThreshold;
  final void Function(int setIdx) onTapCircle;
  final void Function(int setIdx) onLongPressCircle;
  final VoidCallback onTapWarmup;

  /// Called when user changes thresholds inline; args are (newSuccess, newFail).
  final void Function(int success, int fail) onThresholdChanged;

  bool get _allCompleted => tapped.every((t) => t);

  bool get _allSucceeded =>
      _allCompleted && doneReps.every((r) => r >= exercise.reps);

  @override
  Widget build(BuildContext context) {
    Color headerColor = Colors.grey.shade800;
    if (_allCompleted) {
      headerColor =
          _allSucceeded ? Colors.green.shade800 : Colors.red.shade900;
    }

    return Card(
      color: headerColor,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    exercise.name,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 15,
                    ),
                  ),
                ),
                Text(
                  '${exercise.sets}×${exercise.reps}×${exercise.weight}kg',
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _WarmupRow(
              warmupWeight: exercise.warmupWeight,
              tapped: warmupTapped,
              onTap: onTapWarmup,
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: List.generate(
                exercise.sets,
                (s) => RepCircle(
                  targetReps: exercise.reps,
                  doneReps: doneReps[s],
                  tapped: tapped[s],
                  onTap: () => onTapCircle(s),
                  onLongPress: () => onLongPressCircle(s),
                ),
              ),
            ),
            const Divider(color: Colors.white12, height: 20),
            _ThresholdRow(
              successThreshold: successThreshold,
              failThreshold: failThreshold,
              onSuccessChanged: (v) => onThresholdChanged(v, failThreshold),
              onFailChanged: (v) => onThresholdChanged(successThreshold, v),
            ),
          ],
        ),
      ),
    );
  }
}

class _ThresholdRow extends StatelessWidget {
  const _ThresholdRow({
    required this.successThreshold,
    required this.failThreshold,
    required this.onSuccessChanged,
    required this.onFailChanged,
  });

  final int successThreshold;
  final int failThreshold;
  final ValueChanged<int> onSuccessChanged;
  final ValueChanged<int> onFailChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.trending_up, size: 13, color: Colors.greenAccent),
        const SizedBox(width: 4),
        const Text(
          'after',
          style: TextStyle(color: Colors.white38, fontSize: 11),
        ),
        const SizedBox(width: 6),
        _MiniStepper(
          value: successThreshold,
          onChanged: onSuccessChanged,
        ),
        const SizedBox(width: 4),
        const Text(
          '↑',
          style: TextStyle(color: Colors.white38, fontSize: 11),
        ),
        const Spacer(),
        const Icon(Icons.trending_down, size: 13, color: Colors.redAccent),
        const SizedBox(width: 4),
        const Text(
          'after',
          style: TextStyle(color: Colors.white38, fontSize: 11),
        ),
        const SizedBox(width: 6),
        _MiniStepper(
          value: failThreshold,
          onChanged: onFailChanged,
        ),
        const SizedBox(width: 4),
        const Text(
          '↓',
          style: TextStyle(color: Colors.white38, fontSize: 11),
        ),
      ],
    );
  }
}

class _MiniStepper extends StatelessWidget {
  const _MiniStepper({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  static const _min = 1;
  static const _max = 5;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _btn(Icons.remove, value > _min ? () => onChanged(value - 1) : null),
        SizedBox(
          width: 22,
          child: Text(
            '$value',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white, fontSize: 12),
          ),
        ),
        _btn(Icons.add, value < _max ? () => onChanged(value + 1) : null),
      ],
    );
  }

  Widget _btn(IconData icon, VoidCallback? onTap) => GestureDetector(
        onTap: onTap,
        child: Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            color: Colors.grey.shade700,
            borderRadius: BorderRadius.circular(4),
          ),
          alignment: Alignment.center,
          child: Icon(
            icon,
            size: 12,
            color: onTap != null ? Colors.white : Colors.white24,
          ),
        ),
      );
}

class _WarmupRow extends StatelessWidget {
  const _WarmupRow({
    required this.warmupWeight,
    required this.tapped,
    required this.onTap,
  });

  final double warmupWeight;
  final bool tapped;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Text(
          'Warmup  1×5×',
          style: TextStyle(color: Colors.white54, fontSize: 12),
        ),
        Text(
          '${warmupWeight}kg',
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
        const SizedBox(width: 10),
        GestureDetector(
          onTap: tapped ? null : onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: tapped ? Colors.teal : Colors.transparent,
              border: Border.all(
                color: tapped ? Colors.teal : Colors.white38,
                width: 2,
              ),
            ),
            alignment: Alignment.center,
            child: Icon(
              tapped ? Icons.check : Icons.fitness_center,
              color: tapped ? Colors.white : Colors.white38,
              size: 16,
            ),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          tapped ? 'done' : 'optional',
          style: TextStyle(
            color: tapped ? Colors.tealAccent : Colors.white30,
            fontSize: 11,
          ),
        ),
      ],
    );
  }
}
