import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/map_tile_cache.dart';
import 'package:workout_app/widgets/run_map.dart';

import '_run_map_fixtures.dart';

Future<void> _pump(WidgetTester tester, Widget map) async {
  tester.view.physicalSize = const Size(400, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(themed(map));
  await tester.pump();
  await tester.pump();
}

MapCamera _camera(WidgetTester tester) =>
    MapCamera.of(tester.element(find.byType(RichAttributionWidget)));

void main() {
  group('RunMap.route', () {
    testWidgets('draws one polyline, start and end markers', (tester) async {
      final track = buildTrack();
      await _pump(
        tester,
        RunMap.route(points: track.points, tileProviderOpener: fakeTiles()),
      );
      final line = tester.widget<PolylineLayer>(find.byType(PolylineLayer));
      expect(line.polylines, hasLength(1));
      expect(line.polylines.single.points, hasLength(track.points.length));
      final markers = tester.widget<MarkerLayer>(find.byType(MarkerLayer));
      expect(markers.markers, hasLength(2));
    });

    testWidgets('asks OSM with the real user agent package', (tester) async {
      await _pump(
        tester,
        RunMap.route(
          points: buildTrack().points,
          tileProviderOpener: fakeTiles(),
        ),
      );
      final tiles = tester.widget<TileLayer>(find.byType(TileLayer));
      expect(tiles.urlTemplate, contains('tile.openstreetmap.org'));
      // TileLayer folds userAgentPackageName into the provider's headers.
      expect(
        tiles.tileProvider.headers['User-Agent'],
        contains('com.kuhy.workout_app'),
      );
    });

    testWidgets('fits every point on screen', (tester) async {
      final track = buildTrack();
      await _pump(
        tester,
        RunMap.route(points: track.points, tileProviderOpener: fakeTiles()),
      );
      final camera = _camera(tester);
      final area = Offset.zero & const Size(400, 600);
      for (final p in track.points) {
        final at = camera.latLngToScreenOffset(
          LatLng(p.latitude, p.longitude),
        );
        expect(area.contains(at), isTrue, reason: '$at is off screen');
      }
    });

    testWidgets('collapsed attribution shows no words until tapped', (
      tester,
    ) async {
      await _pump(
        tester,
        RunMap.route(
          points: buildTrack().points,
          tileProviderOpener: fakeTiles(),
        ),
      );
      // flutter_map keeps the credit in the tree and fades it in on tap, so
      // "no visible words" means: fully transparent until the icon is tapped.
      final credit = find.textContaining('OpenStreetMap');
      expect(find.byType(Text), findsOneWidget);
      double opacity() => tester
          .widget<AnimatedOpacity>(
            find
                .ancestor(of: credit, matching: find.byType(AnimatedOpacity))
                .first,
          )
          .opacity;
      expect(opacity(), 0);
      await tester.tap(find.byIcon(Icons.info_outline));
      await tester.pumpAndSettle();
      expect(opacity(), 1);
    });

    testWidgets('one point: a marker, no line, no crash', (tester) async {
      await _pump(
        tester,
        RunMap.route(
          points: buildTrack(count: 1).points,
          tileProviderOpener: fakeTiles(),
        ),
      );
      expect(find.byType(PolylineLayer), findsNothing);
      expect(
        tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers,
        hasLength(1),
      );
    });

    testWidgets('no points: plain map, no layers', (tester) async {
      await _pump(
        tester,
        RunMap.route(points: const [], tileProviderOpener: fakeTiles()),
      );
      expect(find.byType(PolylineLayer), findsNothing);
      expect(find.byType(MarkerLayer), findsNothing);
      expect(find.byType(FlutterMap), findsOneWidget);
    });

    testWidgets('no tile layer until the provider has opened', (tester) async {
      final opening = Completer<TileProvider>();
      await _pump(
        tester,
        RunMap.route(
          points: buildTrack().points,
          tileProviderOpener: () => opening.future,
        ),
      );
      expect(find.byType(TileLayer), findsNothing);
      expect(find.byType(PolylineLayer), findsOneWidget);
      opening.complete(FakeTileProvider());
      await tester.pump();
      await tester.pump();
      expect(find.byType(TileLayer), findsOneWidget);
    });

    testWidgets('offline: route still drawn, one loud warning', (tester) async {
      final lines = await capturingDebugPrint(() async {
        await _pump(
          tester,
          RunMap.route(
            points: buildTrack().points,
            tileProviderOpener: fakeTiles(offline: true),
          ),
        );
        await tester.pump(const Duration(milliseconds: 100));
      });
      expect(find.byType(PolylineLayer), findsOneWidget);
      final warnings = lines.where((l) => l.contains('WARNING'));
      expect(warnings, hasLength(1), reason: lines.join('\n'));
      expect(warnings.single, contains('plain background'));
    });
  });

  group('RunMap.live', () {
    testWidgets('follows the last point and draws as the track grows', (
      tester,
    ) async {
      final track = ValueNotifier<RunTrack?>(null);
      addTearDown(track.dispose);
      await _pump(
        tester,
        RunMap.live(trackListenable: track, tileProviderOpener: fakeTiles()),
      );
      expect(find.byType(PolylineLayer), findsNothing);
      expect(find.byType(MarkerLayer), findsNothing);

      final full = buildTrack(count: 4);
      track.value = full;
      await tester.pump();
      expect(find.byType(PolylineLayer), findsOneWidget);
      expect(
        tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers,
        hasLength(2),
      );
      final last = full.points.last;
      final center = _camera(tester).center;
      expect(center.latitude, closeTo(last.latitude, 1e-6));
      expect(center.longitude, closeTo(last.longitude, 1e-6));
      expect(find.byIcon(Icons.my_location), findsNothing);
    });

    testWidgets('a drag ends follow mode, the button resumes it', (
      tester,
    ) async {
      final full = buildTrack(count: 4);
      final track = ValueNotifier<RunTrack?>(full);
      addTearDown(track.dispose);
      await _pump(
        tester,
        RunMap.live(trackListenable: track, tileProviderOpener: fakeTiles()),
      );
      await tester.drag(find.byType(FlutterMap), const Offset(120, 0));
      await tester.pump();
      expect(find.byIcon(Icons.my_location), findsOneWidget);
      final dragged = _camera(tester).center.longitude;
      expect(dragged, isNot(closeTo(full.points.last.longitude, 1e-6)));

      // New fixes no longer pull the camera while follow is off.
      track.value = buildTrack(count: 6);
      await tester.pump();
      expect(_camera(tester).center.longitude, closeTo(dragged, 1e-9));

      await tester.tap(find.byIcon(Icons.my_location));
      await tester.pump();
      expect(find.byIcon(Icons.my_location), findsNothing);
      final last = track.value!.points.last;
      expect(_camera(tester).center.longitude, closeTo(last.longitude, 1e-6));
    });

    testWidgets('stops listening when disposed', (tester) async {
      final track = ValueNotifier<RunTrack?>(buildTrack());
      addTearDown(track.dispose);
      await _pump(
        tester,
        RunMap.live(trackListenable: track, tileProviderOpener: fakeTiles()),
      );
      await tester.pumpWidget(const SizedBox());
      track.value = buildTrack(count: 7);
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  });
}
