// Shared fixtures for the run map / run detail / history-runs tests.
//
// The map never gets a real tile provider here: [FakeTileProvider] serves a
// 1x1 transparent PNG (or an image that fails to load, to play "offline"),
// so no test can reach tile.openstreetmap.org.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/ui/theme.dart';

final _transparentPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
  '60e6kgAAAABJRU5ErkJggg==',
);

/// An image that always fails, as a tile does with no network and no cache.
class FailingImage extends ImageProvider<FailingImage> {
  /// Creates the failing image.
  const FailingImage();

  @override
  Future<FailingImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(
    FailingImage key,
    ImageDecoderCallback decode,
  ) => OneFrameImageStreamCompleter(
    Future<ImageInfo>.error(StateError('no network')),
  );
}

/// A [TileProvider] that never touches the network.
class FakeTileProvider extends TileProvider {
  /// Serves transparent tiles, or failing ones when [offline].
  FakeTileProvider({this.offline = false});

  /// Whether every tile fails to load.
  final bool offline;

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) =>
      offline ? const FailingImage() : MemoryImage(_transparentPng);
}

/// Opener returning a fresh [FakeTileProvider].
Future<TileProvider> Function() fakeTiles({bool offline = false}) =>
    () async => FakeTileProvider(offline: offline);

/// A track of [count] fixes heading north-east from Warsaw.
RunTrack buildTrack({
  int count = 5,
  RunSport sport = RunSport.running,
  RunSource source = RunSource.app,
  DateTime? startedAt,
  double distanceM = 5200,
  int totalSeconds = 1930,
}) {
  final start = startedAt ?? DateTime.utc(2026, 11, 10, 6, 30);
  return RunTrack.started(
    sport: sport,
    startedAt: start,
    totalSeconds: totalSeconds,
    distanceM: distanceM,
    source: source,
    points: [
      for (var i = 0; i < count; i++)
        RunPoint(
          time: start.add(Duration(seconds: i * 10)),
          latitude: 52.2297 + i * 0.001,
          longitude: 21.0122 + i * 0.0015,
          distanceM: i * 100.0,
        ),
    ],
  );
}

/// Wraps [child] in the app theme, filling a phone-sized surface.
Widget themed(Widget child) =>
    MaterialApp(theme: buildAppTheme(), home: child);

/// Runs [body] and returns every `debugPrint` line it wrote.
///
/// Restored before returning: the test binding fails a test that leaves
/// `debugPrint` swapped, and it checks that before any tearDown runs.
Future<List<String>> capturingDebugPrint(Future<void> Function() body) async {
  final lines = <String>[];
  final original = debugPrint;
  debugPrint = (message, {wrapWidth}) => lines.add(message ?? '');
  try {
    await body();
  } finally {
    debugPrint = original;
  }
  return lines;
}

/// Registers the SDK's Roboto as the test font, so widths mean something.
///
/// The default test font draws every glyph one em wide; this is the same
/// loader as in `workout_layout_test.dart`.
Future<void> loadRoboto() async {
  final cache = File(Platform.resolvedExecutable).parent.parent.parent.parent;
  final loader = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    final ttf = File(
      '${cache.path}/artifacts/material_fonts/Roboto-$weight.ttf',
    );
    loader.addFont(Future.value(ByteData.sublistView(ttf.readAsBytesSync())));
  }
  await loader.load();
}
