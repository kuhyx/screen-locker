/// Shared fakes for the run recorder, controller and screen tests.
library;

import 'dart:async';

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// One degree of latitude in metres, so tests place fixes by distance.
const double kDegM = 111194.9;

/// A fix [seconds] after 12:00:00 UTC, [northM] metres north of the origin.
GpsFix fixAt(
  int seconds,
  double northM, {
  double accuracy = 5,
  bool mocked = false,
}) => GpsFix(
  time: DateTime.utc(2026, 11, 9, 12).add(Duration(seconds: seconds)),
  latitude: 48.8584 + northM / kDegM,
  longitude: 2.2945,
  altitudeM: 30,
  accuracyM: accuracy,
  isMocked: mocked,
);

/// [count] fixes 2 s apart moving north at 3 m/s (a 10.8 km/h run).
List<GpsFix> straightRun(int count, {int startSecond = 0}) => [
  for (var i = 0; i < count; i++)
    fixAt(startSecond + i * 2, (startSecond + i * 2) * 3.0),
];

/// A source the test feeds by hand, so a pause can fall between two fixes.
class ManualPositionSource implements PositionSource {
  /// Creates a source answering [access].
  ManualPositionSource({this.access = LocationAccess.granted});

  /// What [requestAccess] answers.
  final LocationAccess access;

  /// The stream the recorder listens to.
  final controller = StreamController<GpsFix>.broadcast();

  /// How many times [fixes] was called.
  int subscriptions = 0;

  @override
  Future<LocationAccess> requestAccess() async => access;

  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) {
    subscriptions++;
    return controller.stream;
  }
}

/// A small stored-run shaped track starting at [start] (UTC).
RunTrack sampleTrack({String start = '2026-11-09T12:00:00Z'}) {
  final t = DateTime.parse(start);
  return RunTrack.started(
    sport: RunSport.running,
    startedAt: t,
    totalSeconds: 20,
    distanceM: 60,
    points: [
      for (var i = 0; i < 3; i++)
        RunPoint(
          time: t.add(Duration(seconds: i * 10)),
          latitude: 48.8584 + i * 0.00027,
          longitude: 2.2945,
          altitudeM: 31,
          distanceM: i * 30.0,
        ),
    ],
  );
}
