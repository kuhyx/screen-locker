import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source_geolocator.dart';
import 'package:workout_app/services/position_source_scripted.dart';
import 'package:workout_app/services/run_math.dart';

void main() {
  tearDown(() {
    Sandbox.enabled = false;
    Sandbox.runReplayFactor = Sandbox.defaultReplayFactor;
  });

  final start = DateTime.utc(2026, 11, 10, 8);

  test('the loop is a legal ~4 km track for the filter', () {
    final fixes = sandboxLoopFixes(start);
    final filter = GpsFilter();
    for (final fix in fixes) {
      expect(filter.add(fix), FixVerdict.accepted);
    }
    expect(filter.distanceM, closeTo(kLoopLengthM, 20));
    expect(movingSeconds(filter.points), fixes.length * 2 - 2);
    expect(fixes.first.time, start);
    // A closed loop: the lap ends where it began.
    expect(
      haversineM(
        fixes.first.latitude,
        fixes.first.longitude,
        fixes.last.latitude,
        fixes.last.longitude,
      ),
      lessThan(5),
    );
  });

  test('the lap runs at 10 km/h (24 minutes of fixes)', () {
    final lap = sandboxLoopFixes(start);
    expect(lap.last.time.difference(start), const Duration(minutes: 24));
  });

  test('replay times follow the start, so two replays never share an id', () {
    final a = sandboxLoopFixes(start);
    final b = sandboxLoopFixes(start.add(const Duration(seconds: 1)));
    expect(RunTrack.idFor(a.first.time), isNot(RunTrack.idFor(b.first.time)));
  });

  test('the speed-up divides the 2 s fix interval', () async {
    for (final (factor, micros) in [(1, 2000000), (10, 200000), (60, 33333)]) {
      Sandbox.runReplayFactor = factor;
      final source = sandboxRunSource(now: start);
      expect(source, isA<ScriptedPositionSource>());
      expect(
        (source as ScriptedPositionSource).fixDelay,
        Duration(microseconds: micros),
      );
    }
  });

  test('the default speed-up replays a whole run in under a minute', () {
    expect(Sandbox.runReplayFactor, 60);
    final fixes = sandboxLoopFixes(start).length;
    expect(fixes * 2 / Sandbox.runReplayFactor, lessThan(60));
    expect(Sandbox.replayFactors, [1, 10, 60]);
  });

  test('the sandbox replays; the daily build reads the real GPS', () async {
    Sandbox.enabled = true;
    expect(positionSourceFor(), isA<ScriptedPositionSource>());
    Sandbox.enabled = false;
    expect(positionSourceFor(), isA<GeolocatorPositionSource>());
  });

  test('the idle position is the replay first fix, and only that', () async {
    Sandbox.enabled = true;
    final source = idlePositionSourceFor(now: start);
    final fixes = await source.fixes().toList();
    expect(fixes, hasLength(1));
    final first = sandboxLoopFixes(start).first;
    expect(fixes.single.latitude, first.latitude);
    expect(fixes.single.longitude, first.longitude);
    expect((await source.requestAccess()).isGranted, isTrue);
    Sandbox.enabled = false;
    expect(idlePositionSourceFor(), isA<GeolocatorPositionSource>());
  });
}
