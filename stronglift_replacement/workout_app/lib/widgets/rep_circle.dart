/// Tappable circle widget representing one set of an exercise.
///
/// States:
///   neutral  – white, shows target reps, not yet acted upon
///   success  – green, shows target reps (full set done)
///   partial  – orange, shows how many reps were actually done (< target)
///   failed   – red, shows 0 (all reps deducted)
///
/// Interaction:
///   single tap  → neutral→success, success→partial(-1 rep),
///                  partial→partial(-1 rep), failed stays failed
///   long press  → reset to neutral
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Visual state of a [RepCircle].
enum RepCircleState {
  /// Not yet tapped; shows target reps.
  neutral,

  /// All reps completed; green.
  success,

  /// Some reps completed; orange, shows actual count.
  partial,

  /// All reps deducted; red.
  failed,
}

/// Tappable circle representing one working set of an exercise.
class RepCircle extends StatelessWidget {
  /// Creates a [RepCircle].
  const RepCircle({
    required this.targetReps,
    required this.doneReps,
    required this.tapped,
    required this.onTap,
    required this.onLongPress,
    super.key,
  });

  /// Number of reps the user is aiming for this set.
  final int targetReps;

  /// Reps currently registered (may be < targetReps after repeated taps).
  final int doneReps;

  /// Whether this circle has been tapped at all (neutral vs success).
  final bool tapped;

  /// Called on a single tap.
  final VoidCallback onTap;

  /// Called on a long press (resets to neutral).
  final VoidCallback onLongPress;

  RepCircleState get _state {
    if (!tapped) return RepCircleState.neutral;
    if (doneReps >= targetReps) return RepCircleState.success;
    if (doneReps > 0) return RepCircleState.partial;
    return RepCircleState.failed;
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final state = _state;
    // on-fill: this circle is a solid filled surface — text on it always
    // needs dark (ink) text, never the page's near-white text-on-dark.
    final fg = colorScheme.onPrimary;
    final Color bg;
    final String label;

    switch (state) {
      case RepCircleState.neutral:
        // Not yet acted upon — a near-white fill (not pure Colors.white)
        // still reads as "the bright/blank one" against the dark page.
        bg = colorScheme.onSurface;
        label = '$targetReps';
      case RepCircleState.success:
        bg = status.success;
        label = '$targetReps';
      case RepCircleState.partial:
        bg = status.warning;
        label = '$doneReps';
      case RepCircleState.failed:
        bg = colorScheme.error;
        label = '0';
    }

    return GestureDetector(
      onTap: onTap,
      onLongPress: onLongPress,
      child: Container(
        width: 52,
        height: 52,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: bg,
          border: Border.all(
            color: state == RepCircleState.neutral ? colorScheme.outline : bg,
            width: 2,
          ),
          // No shadow (rule 26: dark surfaces never shadow) — the fill
          // color already differentiates this circle from the page.
        ),
        alignment: Alignment.center,
        child: Text(
          label,
          style: TextStyle(
            color: fg,
            fontWeight: FontWeight.bold,
            fontSize: AppTextSize.body,
          ),
        ),
      ),
    );
  }
}
