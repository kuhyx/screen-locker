/// The one place the run host meets `RunRecorder`: an adapter from the
/// recorder's API to [RunEngine].
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_recorder.dart';

/// A [RunEngine] over a [RunRecorder].
class RunRecorderEngine implements RunEngine {
  /// Wraps [recorder].
  RunRecorderEngine(this._recorder);

  final RunRecorder _recorder;

  @override
  RunPhase get phase => _recorder.phase;

  @override
  RunIssue get issue => _recorder.issue;

  @override
  List<RunPoint> get points => _recorder.livePoints.value;

  @override
  int get seconds => _recorder.seconds;

  @override
  double get distanceM => _recorder.distanceM;

  @override
  int? get paceTarget => _recorder.coach.target;

  @override
  double? get pace => _recorder.coach.pace;

  @override
  PaceBand? get band => _recorder.coach.band;

  @override
  RunCheckpoint? checkpoint() => _recorder.checkpoint();

  @override
  Future<bool> start() => _recorder.start();

  @override
  Future<bool> restore(RunCheckpoint checkpoint) =>
      _recorder.restore(checkpoint);

  @override
  void pause() => _recorder.pause();

  @override
  void resume() => _recorder.resume();

  @override
  void setPaceTarget(int? seconds) => _recorder.setPaceTarget(seconds);

  @override
  Future<RunTrack?> finish() => _recorder.finish();

  @override
  void dispose() => _recorder.dispose();

  @override
  void addListener(VoidCallback listener) => _recorder.addListener(listener);

  @override
  void removeListener(VoidCallback listener) =>
      _recorder.removeListener(listener);
}

/// Builds recorders over [sourceFor]; [clock] and [autoEndAfter] are the
/// recorder's own seams (shrunk by tests and the sandbox).
RunEngineFactory recorderEngineFactory(
  PositionSource Function() sourceFor, {
  DateTime Function() clock = DateTime.now,
  Duration autoEndAfter = const Duration(hours: 5),
}) =>
    (hooks) => RunRecorderEngine(
      RunRecorder(
        sourceFor: sourceFor,
        onKilometre: hooks.onKilometre,
        onPaceCue: hooks.onPaceCue,
        onSuggestFinish: (why) => hooks.onSuggest(why.name),
        onAutoEnd: hooks.onAutoEnd,
        clock: clock,
        autoEndAfter: autoEndAfter,
      ),
    );
