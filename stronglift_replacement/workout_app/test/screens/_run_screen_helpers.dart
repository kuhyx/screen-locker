// Pieces of the run screen harness that do not need a recorder.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:material_ui/material_ui.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_target_store.dart';
import 'package:workout_app/widgets/run_map_slot.dart';

import '../widgets/_run_map_fixtures.dart';

/// An in-memory [PaceTargetStore].
class MemoryPaceStore implements PaceTargetStore {
  /// The stored target.
  int value = kDefaultPaceTarget;

  /// How many times [save] ran.
  int saves = 0;

  @override
  Future<int> load() async => value;

  @override
  Future<void> save(int seconds) async {
    saves++;
    value = seconds;
  }
}

/// The real map slot over fake tiles, so nothing reaches the network.
Widget fakeTileMap(
  BuildContext context,
  ValueListenable<List<RunPoint>> points,
  ValueListenable<LatLng?> position,
) => RunMapSlot(
  points: points,
  position: position,
  tileProviderOpener: fakeTiles(),
);

Finder key(String id) => find.byKey(Key(id));

Future<void> tapKey(WidgetTester tester, String id) async {
  await tester.tap(key(id));
  // Stream cancel only completes on the real event loop, so give it a turn
  // before settling the frames.
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 10)),
  );
  await tester.pumpAndSettle();
}
