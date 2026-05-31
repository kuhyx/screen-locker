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
    required this.onTapCircle,
    required this.onLongPressCircle,
    required this.onTapWarmup,
  });

  final Exercise exercise;

  /// tapped[setIdx] - whether each main set circle has been tapped.
  final List<bool> tapped;

  /// doneReps[setIdx] - how many reps recorded for each set.
  final List<int> doneReps;

  final bool warmupTapped;

  final void Function(int setIdx) onTapCircle;
  final void Function(int setIdx) onLongPressCircle;
  final VoidCallback onTapWarmup;

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
            // Header row: name + target
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
            // Warmup row
            _WarmupRow(
              warmupWeight: exercise.warmupWeight,
              tapped: warmupTapped,
              onTap: onTapWarmup,
            ),
            const SizedBox(height: 10),
            // Main set circles
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
          ],
        ),
      ),
    );
  }
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
