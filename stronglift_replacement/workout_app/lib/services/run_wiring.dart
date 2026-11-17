// coverage:ignore-file
// The composition root of a recording: it only names the real plugin,
// database and GPS. Every decision is in the classes it connects, covered
// against fakes.
/// The real parts a run is built from, installed by `main`.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client_flutter.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_engine_recorder.dart';
import 'package:workout_app/services/run_link.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';

/// Real GPS (or the sandbox replay), the real service and database. On
/// Android the run lives in the service isolate behind a [ServiceRunLink];
/// elsewhere it lives in this isolate behind a loopback.
RunController buildRunController() {
  final client = FlutterForegroundRunClient();
  return RunController(
    idleSourceFor: idlePositionSourceFor,
    service: client,
    link: client.isSupported
        ? ServiceRunLink()
        : LoopbackRunLink.build(
            client: client,
            engineFactory: recorderEngineFactory(positionSourceFor),
            cues: FeedbackCues(AudioPlayer()),
            save: (track) async {
              final result = await saveRecordedRun(
                track,
                storage: StorageService.instance,
                enqueue: RunUploader.instance.uploadPending,
              );
              return (stored: result.stored, reason: result.reason);
            },
          ),
    soundOn: () => StorageService.instance.getSoundEnabled(),
  );
}

/// Installs [buildRunController] as the run screen's default.
void installRunWiring() {
  RunScreen.defaultControllerFactory = buildRunController;
}
