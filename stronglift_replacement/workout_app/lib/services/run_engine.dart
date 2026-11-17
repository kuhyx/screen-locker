/// The recording the run host drives, as an interface.
///
/// The host (service isolate in production) never touches `RunRecorder`
/// directly: every call into it goes through `run_engine_recorder.dart`, so
/// the host is tested against a fake and a change to the recorder lands in one
/// adapter.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_phase.dart';

/// What a recording tells its host while it runs.
class RunEngineHooks {
  /// Creates the hooks.
  const RunEngineHooks({
    required this.onKilometre,
    required this.onPaceCue,
    required this.onSuggest,
    required this.onAutoEnd,
  });

  /// A whole kilometre was credited (1, 2, 3 ...).
  final void Function(int km) onKilometre;

  /// The runner left the pace band.
  final void Function(PaceCue cue) onPaceCue;

  /// Advice to finish, named after the recorder's suggestion
  /// (`stationary`, `vehicleSpeed`, `gpsLost`, `restored`). Never ends a run.
  final void Function(String why) onSuggest;

  /// The 5 h limit passed; the host finishes the run like a manual finish.
  final void Function() onAutoEnd;
}

/// One recording: a state machine over a position source.
abstract interface class RunEngine implements Listenable {
  /// Where the recording stands.
  RunPhase get phase;

  /// The current problem, or [RunIssue.none].
  RunIssue get issue;

  /// Accepted points so far, oldest first.
  List<RunPoint> get points;

  /// Credited moving time in seconds.
  int get seconds;

  /// Credited distance in metres.
  double get distanceM;

  /// The pace target in seconds per kilometre, or null.
  int? get paceTarget;

  /// The current pace in seconds per kilometre, once warmed up.
  double? get pace;

  /// Where [pace] stands against [paceTarget].
  PaceBand? get band;

  /// A snapshot to rebuild the run from, or null when idle or finished.
  RunCheckpoint? checkpoint();

  /// Asks for access and begins recording; false when refused or busy.
  Future<bool> start();

  /// Resumes the run from [checkpoint] without prompting; false when it
  /// cannot (the reason is logged by the engine).
  Future<bool> restore(RunCheckpoint checkpoint);

  /// Stops crediting until [resume].
  void pause();

  /// Continues after [pause].
  void resume();

  /// Sets the pace target (null turns it off).
  void setPaceTarget(int? seconds);

  /// Ends the recording; the track, or null when there were too few fixes.
  Future<RunTrack?> finish();

  /// Releases the position stream.
  void dispose();
}

/// Builds a fresh engine wired to [hooks].
typedef RunEngineFactory = RunEngine Function(RunEngineHooks hooks);
