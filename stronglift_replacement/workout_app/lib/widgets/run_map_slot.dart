/// The place on the run screen where the live map goes.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/ui/theme.dart';

/// Placeholder for the live map: replace the body of [build] with the map
/// widget, keeping the [ValueListenable] as its source of points.
///
/// `RunScreen` fills this space from `mapBuilder`, defaulting to this widget,
/// so a map can also be dropped in by passing a builder with no edit here.
class RunMapSlot extends StatelessWidget {
  /// Creates the slot; [points] updates with every accepted GPS fix.
  const RunMapSlot({required this.points, super.key});

  /// The accepted points of the run so far, oldest first.
  final ValueListenable<List<RunPoint>> points;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      key: const Key('run_map_slot'),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Center(
        child: Icon(
          Icons.map_outlined,
          size: 48,
          color: scheme.onSurfaceVariant,
          semanticLabel: 'Map',
        ),
      ),
    );
  }
}
