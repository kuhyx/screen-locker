/// Countdown strip permanently reserved at the top of the workout screen.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Fixed-height strip showing a rest countdown and a skip button.
///
/// The strip is always laid out, rest or no rest: an appearing banner used
/// to steal its height from the exercise list and shift every tile down
/// (2026-09-20). Between rests it renders the same shape muted, so starting
/// a rest changes colours and the number, never a position.
class BreakBanner extends StatelessWidget {
  /// Creates a [BreakBanner].
  const BreakBanner({
    required this.active,
    required this.breakRemaining,
    required this.breakLabel,
    required this.onSkip,
    super.key,
  });

  /// Total strip height; a constant so the layout below never depends on
  /// the text metrics of what the strip happens to show.
  static const double height = 64;

  /// Whether a rest is running. When false the strip is muted and Skip is
  /// hidden (its space is kept).
  final bool active;

  /// Seconds remaining in the current break.
  final int breakRemaining;

  /// Display label for the break (e.g. 'Rest' or 'Warmup rest').
  final String breakLabel;

  /// Called when the user taps the Skip button.
  final VoidCallback onSkip;

  String _fmt(int secs) {
    final m = (secs ~/ 60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

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
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  breakLabel,
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
                Text(
                  _fmt(breakRemaining),
                  style: TextStyle(
                    // Warning (caution/pending) while the countdown runs;
                    // muted between rests so the idle strip recedes.
                    color: active
                        ? status.warning
                        : colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.title,
                    fontWeight: FontWeight.bold,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
          ),
          Visibility(
            visible: active,
            maintainSize: true,
            maintainAnimation: true,
            maintainState: true,
            child: TextButton(
              onPressed: onSkip,
              child: Text('Skip', style: TextStyle(color: colorScheme.primary)),
            ),
          ),
        ],
      ),
    );
  }
}
