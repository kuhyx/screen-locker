/// The place on the run screen where the live map goes.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/map_tile_cache.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map.dart';

/// The live map on the run screen: [RunMap.live] over the recorder's points,
/// clipped to the card shape.
///
/// `RunScreen` fills this space from `mapBuilder`, defaulting to this widget.
class RunMapSlot extends StatelessWidget {
  /// Creates the slot; [points] updates with every accepted GPS fix.
  const RunMapSlot({
    required this.points,
    super.key,
    this.tileProviderOpener = openOsmTileProvider,
  });

  /// The accepted points of the run so far, oldest first.
  final ValueListenable<List<RunPoint>> points;

  /// Where the map's tiles come from; tests pass a fake.
  final TileProviderOpener tileProviderOpener;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      key: const Key('run_map_slot'),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      clipBehavior: Clip.antiAlias,
      child: RunMap.live(
        pointsListenable: points,
        tileProviderOpener: tileProviderOpener,
      ),
    );
  }
}
