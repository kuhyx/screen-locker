// One mode: every GPS activity is recorded with the running filter and written
// as a Running TCX. There is no run/walk switch left on the screen.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '../fake_audio_platform.dart';
import '_run_screen_fixtures.dart';

void main() {
  setUp(installFakeAudioPlatform);

  testWidgets('no sport toggle and no sport icon anywhere', (tester) async {
    final h = RunHarness();
    await h.pump(tester);
    expect(key('run_sport'), findsNothing);
    expect(find.byType(SegmentedButton<RunSport>), findsNothing);
    expect(find.byIcon(Icons.directions_walk), findsNothing);
    expect(find.byIcon(Icons.directions_run), findsNothing);
    await tapKey(tester, 'run_start');
    expect(find.byIcon(Icons.directions_walk), findsNothing);
    expect(find.byIcon(Icons.directions_run), findsNothing);
  });

  testWidgets('the saved track is a Running TCX with a _Running file name', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    // 3 m/s is 10.8 km/h: over any walking cap, fine for the running filter.
    await h.run(tester, 30);
    await tapKey(tester, 'run_finish');

    final track = h.saved.single;
    expect(track.sport, RunSport.running);
    expect(track.distanceM, greaterThan(150));
    expect(tcxFilename(track), endsWith('_Running.tcx'));
    expect(encodeTcx(track), contains('Sport="Running"'));
    expect(encodeTcx(track), isNot(contains('Walking')));
  });
}
