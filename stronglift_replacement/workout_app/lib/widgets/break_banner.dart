/// Countdown banner displayed at the top of the workout screen during a rest.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Banner widget showing a break countdown and a skip button.
class BreakBanner extends StatelessWidget {
  /// Creates a [BreakBanner].
  const BreakBanner({
    required this.breakRemaining,
    required this.breakLabel,
    required this.onSkip,
    super.key,
  });

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
      // Elevation via fill step (ink-raised-2), not a shadow — differentiates
      // the banner from the page without a saturated attention-grabbing fill.
      color: colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
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
                    // Warning (caution/pending) — this is a running countdown.
                    color: status.warning,
                    fontSize: AppTextSize.title,
                    fontWeight: FontWeight.bold,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: onSkip,
            child: Text('Skip', style: TextStyle(color: colorScheme.primary)),
          ),
        ],
      ),
    );
  }
}
