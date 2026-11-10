/// A recording fake for the run foreground service.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/pace_band.dart';

/// Stands in for `flutter_foreground_task` on the run screen's side.
class FakeForegroundRunClient implements ForegroundRunClient {
  /// Creates a fake describing a healthy Android device.
  FakeForegroundRunClient({
    this.isSupported = true,
    this.permissionGranted = true,
    this.grantOnRequest = true,
    this.startSucceeds = true,
    this.onStart,
  });

  @override
  bool isSupported;

  /// Whether notifications are already allowed.
  bool permissionGranted;

  /// Whether asking for them succeeds.
  bool grantOnRequest;

  /// Whether the service starts.
  bool startSucceeds;

  /// Runs inside [start], to record what had happened by then.
  void Function()? onStart;

  /// `withLocation` of each start.
  final starts = <bool>[];

  /// Notification redraws as `title|text`, the first being the start.
  final drawn = <String>[];

  /// Calls recorded in order.
  final calls = <String>[];

  @override
  Future<bool> hasNotificationPermission() async {
    calls.add('has');
    return permissionGranted;
  }

  @override
  Future<bool> requestNotificationPermission() async {
    calls.add('request');
    return permissionGranted = grantOnRequest;
  }

  @override
  Future<bool> start({
    required bool withLocation,
    required String title,
    required String text,
  }) async {
    calls.add('start');
    onStart?.call();
    starts.add(withLocation);
    drawn.add('$title|$text');
    return startSucceeds;
  }

  @override
  Future<void> update({required String title, required String text}) async {
    drawn.add('$title|$text');
  }

  @override
  Future<void> stop() async => calls.add('stop');
}

/// Cues that touch neither the database nor a speaker, and count kilometres.
class QuietCues extends FeedbackCues {
  /// Creates cues over a player (needs the fake audio platform installed).
  QuietCues() : super(AudioPlayer());

  /// Kilometres announced.
  final kilometres = <int>[];

  /// How many times the finish cue fired.
  int finishes = 0;

  /// Pace cues given, in order.
  final paceCues = <PaceCue>[];

  @override
  Future<void> load() async {}

  @override
  Future<void> paceOff(PaceCue cue) async => paceCues.add(cue);

  @override
  Future<void> kilometreReached(int km) async => kilometres.add(km);

  @override
  Future<void> workoutFinished() async => finishes++;
}
