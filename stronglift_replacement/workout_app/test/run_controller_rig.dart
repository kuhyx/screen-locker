/// A [RunController] over the real recorder behind the in-process host.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart' show addTearDown;
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_engine_recorder.dart';
import 'package:workout_app/services/run_host.dart';
import 'package:workout_app/services/run_link.dart';

import 'fake_run_service.dart';
import 'run_test_fixtures.dart';

/// Builds the controller; the host (which keeps a watchdog timer while a run
/// is active) is released at the end of the test.
RunController buildRunController({
  required ManualPositionSource source,
  PositionSource Function()? idleSourceFor,
  FeedbackCues? cues,
  FakeForegroundRunClient? service,
  RunSaveFn? save,
  List<RunTrack>? saved,
}) {
  final client = service ?? FakeForegroundRunClient();
  final link = LoopbackRunLink.build(
    client: client,
    engineFactory: recorderEngineFactory(() => source),
    cues: cues ?? FeedbackCues(AudioPlayer()),
    save:
        save ??
        (track) async {
          saved?.add(track);
          return (stored: true, reason: 'saved');
        },
  );
  addTearDown(link.host.dispose);
  return RunController(
    idleSourceFor: idleSourceFor ?? () => source,
    service: client,
    link: link,
    soundOn: () async => true,
    retryEvery: const Duration(milliseconds: 1),
  );
}

/// A link to nobody: commands vanish and nothing ever answers.
class SilentLink implements RunHostLink {
  @override
  Stream<Map<Object?, Object?>> get messages => const Stream.empty();

  @override
  void send(Map<String, Object?> command) {}

  @override
  Future<void> close() async {}
}

/// A controller whose host is down.
RunController buildSilentController() => RunController(
  idleSourceFor: ManualPositionSource.new,
  service: FakeForegroundRunClient(isSupported: false),
  link: SilentLink(),
  soundOn: () async => true,
  hostTimeout: const Duration(milliseconds: 50),
  retryEvery: const Duration(milliseconds: 1),
);
