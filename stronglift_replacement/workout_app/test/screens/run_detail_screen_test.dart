import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/screens/run_detail_screen.dart';
import 'package:workout_app/widgets/run_map.dart';

import '../widgets/_run_map_fixtures.dart';

// Pixel 6a, physical px (adb dumpsys window), per build-mobile-app R7.
const _phonePhysical = Size(1080, 2400);
const _phoneDpr = 2.625;

Future<void> _pump(WidgetTester tester, RunTrack track) async {
  await tester.pumpWidget(
    themed(RunDetailScreen(track: track, tileProviderOpener: fakeTiles())),
  );
  await tester.pump();
  await tester.pump();
}

void _phone(WidgetTester tester) {
  tester.view.physicalSize = _phonePhysical;
  tester.view.devicePixelRatio = _phoneDpr;
  tester.view.padding = const FakeViewPadding(top: 132, bottom: 63);
  addTearDown(tester.view.reset);
}

void main() {
  setUpAll(loadRoboto);

  testWidgets('shows the route map and the four numbers', (tester) async {
    _phone(tester);
    final track = buildTrack(startedAt: DateTime(2026, 11, 10, 6, 30).toUtc());
    await _pump(tester, track);
    expect(find.byType(RunMap), findsOneWidget);
    expect(find.text('5.20'), findsOneWidget);
    expect(find.text('32:10'), findsOneWidget);
    expect(find.text('6:11'), findsOneWidget);
    expect(find.text('2026-11-10 06:30'), findsOneWidget);
    expect(find.byIcon(Icons.directions_run), findsOneWidget);
    expect(find.byIcon(Icons.history), findsNothing);
  });

  testWidgets('a walk gets the walking icon, an import the history mark', (
    tester,
  ) async {
    _phone(tester);
    await _pump(
      tester,
      buildTrack(sport: RunSport.walking, source: RunSource.runnerupImport),
    );
    expect(find.byIcon(Icons.directions_walk), findsOneWidget);
    expect(find.byIcon(Icons.directions_run), findsNothing);
    expect(find.byIcon(Icons.history), findsOneWidget);
  });

  testWidgets('no words: every visible text is digits and separators', (
    tester,
  ) async {
    _phone(tester);
    await _pump(tester, buildTrack(totalSeconds: 3725));
    final numeric = RegExp(r'^[0-9:.\- ]+$');
    final words = tester
        .widgetList<Text>(find.byType(Text))
        .map((t) => t.data ?? '')
        // The OSM credit is mandatory; it is fully transparent until the
        // collapsed info icon is tapped (see run_map_test.dart).
        .where((t) => !numeric.hasMatch(t) && !t.contains('OpenStreetMap'));
    expect(words, isEmpty);
    expect(find.text('1:02:05'), findsOneWidget);
  });

  testWidgets('a zero-distance run has a dash pace, not a crash', (
    tester,
  ) async {
    _phone(tester);
    await _pump(tester, buildTrack(count: 1, distanceM: 0, totalSeconds: 0));
    expect(find.text('-:--'), findsOneWidget);
    expect(find.text('0.00'), findsOneWidget);
  });

  testWidgets('the back button leaves the screen', (tester) async {
    _phone(tester);
    final track = buildTrack();
    await tester.pumpWidget(
      themed(
        Builder(
          builder: (context) => TextButton(
            onPressed: () => Navigator.of(context).push<void>(
              MaterialPageRoute(
                builder: (_) => RunDetailScreen(
                  track: track,
                  tileProviderOpener: fakeTiles(),
                ),
              ),
            ),
            child: const Icon(Icons.add),
          ),
        ),
      ),
    );
    await tester.tap(find.byIcon(Icons.add));
    await tester.pumpAndSettle();
    expect(find.byType(RunDetailScreen), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();
    expect(find.byType(RunDetailScreen), findsNothing);
  });

  testWidgets('Pixel 6a insets: one screen, nothing scrolls', (tester) async {
    _phone(tester);
    await _pump(tester, buildTrack(totalSeconds: 3725));
    final scrollables = tester.stateList<ScrollableState>(
      find.byType(Scrollable),
    );
    for (final s in scrollables) {
      expect(s.position.maxScrollExtent, 0);
    }
    // With no list on the screen the loop above is vacuously true, so also
    // pin the geometry: panel above the nav bar, back button below the
    // status bar.
    final viewport = _phonePhysical / _phoneDpr;
    final panel = tester.getRect(find.byKey(const Key('run_stats_panel')));
    expect(panel.bottom, lessThanOrEqualTo(viewport.height - 63 / _phoneDpr));
    expect(panel.left, greaterThanOrEqualTo(0));
    expect(panel.right, lessThanOrEqualTo(viewport.width));
    final back = tester.getRect(find.byIcon(Icons.arrow_back));
    expect(back.top, greaterThanOrEqualTo(132 / _phoneDpr));
    expect(tester.takeException(), isNull);
  });
}
