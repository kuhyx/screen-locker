/// The one-line PC status on the workout summary.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/ui/theme.dart';

/// Shows "PC: applying…" until [poke] resolves, then its [PokeResult.label].
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
              Text(
                'PC: applying…',
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  fontSize: AppTextSize.caption,
                ),
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
        return Text(
          result.label,
          key: const Key('pc-poke-result'),
          style: TextStyle(color: color, fontSize: AppTextSize.caption),
        );
      },
    );
  }
}
