/// Countdown strip permanently reserved at the top of the workout screen.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Fixed-height strip: the rest countdown, Skip, and the workout's Reset and
/// Finish actions.
///
/// The strip is always laid out, rest or no rest: an appearing banner used
/// to steal its height from the exercise list and shift every tile down
/// (2026-09-20). Between rests it renders the same shape muted, so starting
/// a rest changes colours and the number, never a position. The same holds
/// for the buttons: a hidden one keeps its space.
///
/// There is no label. The colour of the number already says whether a rest
/// is running, and "Rest (5 min — keep going!)" only cost height (2026-09-27).
class BreakBanner extends StatelessWidget {
  /// Creates a [BreakBanner].
  const BreakBanner({
    required this.active,
    required this.breakRemaining,
    required this.onSkip,
    required this.finished,
    required this.canFinish,
    required this.onReset,
    required this.onFinish,
    super.key,
  });

  /// Total strip height; a constant so the layout below never depends on
  /// the text metrics of what the strip happens to show.
  static const double height = 56;

  /// Whether a rest is running. When false the countdown is muted and Skip
  /// is hidden (its space is kept).
  final bool active;

  /// Seconds remaining in the current break.
  final int breakRemaining;

  /// Called when the user taps the Skip button.
  final VoidCallback onSkip;

  /// Whether the workout is over; hides Reset and Finish (space kept).
  final bool finished;

  /// Whether every set is recorded; Finish is disabled until it is.
  final bool canFinish;

  /// Called when the user taps Reset.
  final VoidCallback onReset;

  /// Called when the user taps Finish.
  final VoidCallback onFinish;

  String _fmt(int secs) {
    final m = (secs ~/ 60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  /// [child] when [visible], otherwise the same box left empty.
  static Widget _slot({required bool visible, required Widget child}) =>
      Visibility(
        visible: visible,
        maintainSize: true,
        maintainAnimation: true,
        maintainState: true,
        child: child,
      );

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return Container(
      height: height,
      // Elevation via fill step (ink-raised-2), not a shadow — differentiates
      // the banner from the page without a saturated attention-grabbing fill.
      color: colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          Text(
            _fmt(breakRemaining),
            style: TextStyle(
              // Warning (caution/pending) while the countdown runs; muted
              // between rests so the idle strip recedes.
              color: active ? status.warning : colorScheme.onSurfaceVariant,
              fontSize: AppTextSize.title,
              fontWeight: FontWeight.bold,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          const Spacer(),
          _slot(
            visible: active,
            child: TextButton(
              onPressed: onSkip,
              child: Text('Skip', style: TextStyle(color: colorScheme.primary)),
            ),
          ),
          _slot(
            visible: !finished,
            child: TextButton(
              onPressed: onReset,
              child: Text('Reset', style: TextStyle(color: colorScheme.error)),
            ),
          ),
          _slot(
            visible: !finished,
            child: TextButton(
              onPressed: canFinish ? onFinish : null,
              child: Text(
                'Finish',
                style: TextStyle(
                  color: canFinish
                      ? status.success
                      : colorScheme.onSurfaceVariant,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
