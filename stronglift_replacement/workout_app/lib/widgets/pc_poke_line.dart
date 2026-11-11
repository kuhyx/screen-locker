/// The one-line PC status on the workout summary.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/ui/theme.dart';

/// A spinner until [poke] resolves, then a PC glyph, an outcome glyph and
/// the numbers the PC sent back. [PokeResult.label] is the spoken label.
///
/// The service bounds [poke] to 2 s, so this never spins forever: an
/// unreachable PC turns into the sync fallback line on its own.
class PcPokeLine extends StatelessWidget {
  /// Creates the line for an in-flight [poke].
  const PcPokeLine({required this.poke, super.key});

  /// The poke started when the workout finished.
  final Future<PokeResult> poke;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return FutureBuilder<PokeResult>(
      future: poke,
      builder: (context, snapshot) {
        final result = snapshot.data;
        if (result == null) {
          return Row(
            key: const Key('pc-poke-pending'),
            children: [
              SizedBox.square(
                dimension: AppTextSize.caption,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // textgate: was "PC: applying…".
              Icon(
                Icons.computer,
                size: AppTextSize.body,
                color: colorScheme.onSurfaceVariant,
                semanticLabel: 'PC: applying…',
              ),
            ],
          );
        }
        final color = switch (result.outcome) {
          PokeOutcome.credited || PokeOutcome.sandbox => status.success,
          PokeOutcome.duplicate ||
          PokeOutcome.alreadyPaidToday => colorScheme.onSurfaceVariant,
          PokeOutcome.notCounted || PokeOutcome.failed => status.warning,
        };
        // textgate: was the sentence in [PokeResult.label]; now PC glyph +
        // outcome glyph + the PC's own numbers, outcome colour as channel 2.
        final glyph = switch (result.outcome) {
          PokeOutcome.credited || PokeOutcome.sandbox => Icons.check_circle,
          PokeOutcome.duplicate ||
          PokeOutcome.alreadyPaidToday => Icons.done_all,
          PokeOutcome.notCounted => Icons.block,
          PokeOutcome.failed => Icons.schedule,
        };
        final style = TextStyle(color: color, fontSize: AppTextSize.caption);
        final minutes = result.gamingBudgetMinutes;
        return Semantics(
          label: result.label,
          excludeSemantics: true,
          child: Row(
            key: const Key('pc-poke-result'),
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.computer, size: AppTextSize.body, color: color),
              const SizedBox(width: AppSpacing.xs),
              Icon(glyph, size: AppTextSize.body, color: color),
              if (result.outcome == PokeOutcome.credited) ...[
                if (result.shutdown != null) ...[
                  const SizedBox(width: AppSpacing.sm),
                  Icon(Icons.power_settings_new, size: 14, color: color),
                  Text(' ${result.shutdown}', style: style),
                ],
                if (minutes != null) ...[
                  const SizedBox(width: AppSpacing.sm),
                  Icon(Icons.sports_esports, size: 14, color: color),
                  Text(' ${(minutes / 60).toStringAsFixed(1)}h', style: style),
                ],
              ],
              // Sandbox: the round trip in milliseconds behind a timer glyph.
              if (result.outcome == PokeOutcome.sandbox) ...[
                const SizedBox(width: AppSpacing.sm),
                Icon(Icons.timer, size: 14, color: color),
                Text(' ${result.roundTripMs ?? 0}', style: style),
              ],
            ],
          ),
        );
      },
    );
  }
}
