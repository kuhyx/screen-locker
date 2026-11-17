/// A hand-driven [RunEngine] for the host, controller and screen tests.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_phase.dart';

/// A checkpoint the tests only need to hand around.
class FakeCheckpoint implements RunCheckpoint {
  /// Creates one marked with [tag].
  FakeCheckpoint(this.tag);

  /// Which snapshot this is.
  final int tag;

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Records what the host asked of it; the test moves it along.
class FakeRunEngine extends ChangeNotifier implements RunEngine {
  /// Creates an idle engine; [startResult] is what [start] answers.
  FakeRunEngine({this.startResult = true, this.restoreResult = true});

  /// Answer of [start].
  bool startResult;

  /// Answer of [restore].
  bool restoreResult;

  /// How many times [start] ran.
  int starts = 0;

  /// The checkpoints handed to [restore].
  final restored = <RunCheckpoint>[];

  /// Whether [dispose] ran.
  bool disposed = false;

  /// What [finish] returns.
  RunTrack? track;

  /// Calls in order, for ordering assertions.
  final calls = <String>[];

  RunPhase _phase = RunPhase.idle;
  RunIssue _issue = RunIssue.none;
  final _points = <RunPoint>[];
  int _checkpoints = 0;

  @override
  RunPhase get phase => _phase;

  @override
  RunIssue get issue => _issue;

  @override
  List<RunPoint> get points => List.unmodifiable(_points);

  @override
  int get seconds => _points.length * 2;

  @override
  double get distanceM => _points.length * 6.0;

  @override
  int? paceTarget;

  @override
  double? get pace => null;

  @override
  PaceBand? get band => null;

  /// Sets the phase and tells the listeners.
  void setPhase(RunPhase phase, {RunIssue issue = RunIssue.none}) {
    _phase = phase;
    _issue = issue;
    notifyListeners();
  }

  /// One accepted fix 6 m further on.
  void addFix() {
    final n = _points.length;
    _points.add(
      RunPoint(
        time: DateTime.utc(2026, 11, 9, 12).add(Duration(seconds: n * 2)),
        latitude: 48.8584 + n * 0.00005,
        longitude: 2.2945,
        distanceM: n * 6.0,
      ),
    );
    notifyListeners();
  }

  @override
  RunCheckpoint? checkpoint() =>
      _phase.isActive ? FakeCheckpoint(++_checkpoints) : null;

  @override
  Future<bool> start() async {
    starts++;
    calls.add('start');
    if (!startResult) {
      setPhase(RunPhase.idle, issue: RunIssue.denied);
      return false;
    }
    setPhase(RunPhase.recording);
    return true;
  }

  @override
  Future<bool> restore(RunCheckpoint checkpoint) async {
    restored.add(checkpoint);
    calls.add('restore');
    if (!restoreResult) {
      setPhase(RunPhase.idle, issue: RunIssue.streamError);
      return false;
    }
    setPhase(RunPhase.recording);
    return true;
  }

  @override
  void pause() {
    calls.add('pause');
    setPhase(RunPhase.paused);
  }

  @override
  void resume() {
    calls.add('resume');
    setPhase(RunPhase.recording);
  }

  @override
  void setPaceTarget(int? seconds) {
    paceTarget = seconds;
    calls.add('pace $seconds');
  }

  @override
  Future<RunTrack?> finish() async {
    calls.add('finish');
    setPhase(RunPhase.finished);
    return track;
  }

  @override
  void dispose() {
    disposed = true;
    super.dispose();
  }
}
