// RunMap.live with a current-position listenable: the idle map before a run.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/widgets/run_map.dart';

import '_run_map_fixtures.dart';

const _here = LatLng(50.06, 19.94);
const _there = LatLng(50.07, 19.95);

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

Widget _map(
  ValueNotifier<List<RunPoint>> points,
  ValueNotifier<LatLng?> position,
) => RunMap.live(
  pointsListenable: points,
  positionListenable: position,
  tileProviderOpener: fakeTiles(),
);

void main() {
  late ValueNotifier<List<RunPoint>> points;
  late ValueNotifier<LatLng?> position;

  setUp(() {
    points = ValueNotifier(const []);
    position = ValueNotifier(null);
  });

  tearDown(() {
    points.dispose();
    position.dispose();
  });

  testWidgets('no fix yet: the zoomed-out fallback, no marker', (tester) async {
    await _pump(tester, _map(points, position));
    expect(_camera(tester).zoom, lessThan(8));
    expect(find.byType(MarkerLayer), findsNothing);
  });

  testWidgets('a fix before the map is built starts centred on it', (
    tester,
  ) async {
    position.value = _here;
    await _pump(tester, _map(points, position));
    expect(_camera(tester).center.latitude, closeTo(_here.latitude, 1e-6));
    expect(_camera(tester).zoom, greaterThan(15));
    expect(
      tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers,
      hasLength(1),
    );
  });

  testWidgets('a later fix moves the camera and the marker', (tester) async {
    await _pump(tester, _map(points, position));
    position.value = _here;
    await tester.pump();
    expect(_camera(tester).center.longitude, closeTo(_here.longitude, 1e-6));
    position.value = _there;
    await tester.pump();
    expect(_camera(tester).center.latitude, closeTo(_there.latitude, 1e-6));
    expect(
      tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers.single.point,
      _there,
    );
  });

  testWidgets('recentre jumps to the position with zero run points', (
    tester,
  ) async {
    position.value = _here;
    await _pump(tester, _map(points, position));
    await tester.drag(find.byType(FlutterMap), const Offset(120, 0));
    await tester.pump();
    expect(find.byIcon(Icons.my_location), findsOneWidget);
    expect(
      _camera(tester).center.longitude,
      isNot(closeTo(_here.longitude, 1e-4)),
    );

    await tester.tap(find.byIcon(Icons.my_location));
    await tester.pump();
    expect(_camera(tester).center.latitude, closeTo(_here.latitude, 1e-6));
    expect(_camera(tester).center.longitude, closeTo(_here.longitude, 1e-6));
  });

  testWidgets('once the run has points they win over the position', (
    tester,
  ) async {
    position.value = _here;
    await _pump(tester, _map(points, position));
    final track = buildTrack(count: 4);
    points.value = track.points;
    await tester.pump();
    final last = track.points.last;
    expect(_camera(tester).center.latitude, closeTo(last.latitude, 1e-6));
    // The route's own start and live markers; no extra position marker.
    expect(
      tester.widget<MarkerLayer>(find.byType(MarkerLayer)).markers,
      hasLength(2),
    );
  });

  testWidgets('detail mode ignores any position', (tester) async {
    await _pump(
      tester,
      RunMap.route(points: const [], tileProviderOpener: fakeTiles()),
    );
    expect(find.byType(MarkerLayer), findsNothing);
  });
}
