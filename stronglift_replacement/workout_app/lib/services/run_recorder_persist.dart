// Checkpointing and restore: a `part` file so they can use the recorder's
// private state while the recorder itself stays short.
part of 'run_recorder.dart';

/// Persistence of a run across a dead process.
extension RunRecorderPersistence on RunRecorder {
  /// A snapshot to rebuild the run from, or null when idle or finished.
  RunCheckpoint? checkpoint() {
    final filter = _filter;
    if (!_phase.isActive || filter == null) return null;
    return RunCheckpoint(
      startedAt: _startedAt,
      savedAt: _clock(),
      phase: _phase,
      points: filter.points,
      movingSeconds: _moving,
      distanceM: filter.distanceM,
      km: _km,
      segmentBreak: filter.segmentBreak,
      jumps: filter.jumps,
      paceTargetSeconds: coach.target,
    );
  }

  /// Rebuilds the run from [c] after the process died and reopens the
  /// position source (without prompting). The next fix is bridged across the
  /// dead time. Fires [RunRecorder.onSuggestFinish] with
  /// [RunSuggestion.restored], or [RunRecorder.onAutoEnd] at once when 5 h
  /// have passed. False (logged) when the source cannot open or a run is
  /// already going.
  Future<bool> restore(
    RunCheckpoint c, {
    Future<void> Function()? afterAccess,
  }) async {
    if (_phase != RunPhase.idle || _starting) return false;
    _starting = true;
    try {
      final source = sourceFor();
      final filter = GpsFilter.restore(
        points: c.points,
        segmentBreak: c.segmentBreak,
        jumps: c.jumps,
      );
      final access = await source.checkAccess();
      if (!await _open(source, access, afterAccess, filter)) return false;
      _startedAt = c.startedAt;
      _moving = c.movingSeconds;
      _km = c.km;
      coach
        ..setTarget(c.paceTargetSeconds)
        ..restartAt(c.points.length);
      _live.value = c.points;
      _phase = c.phase;
      SandboxLog.event('run restored', {'m': c.distanceM});
      _announce();
      _watch.restored(
        c.startedAt,
        paused: c.phase == RunPhase.paused,
        distanceM: c.distanceM,
      );
      return true;
    } on Object catch (e, stack) {
      logRestoreFailed(e, stack);
      await _sub?.cancel();
      _sub = null;
      _filter = null;
      _phase = RunPhase.idle;
      _issue = RunIssue.streamError;
      _changed();
      return false;
    } finally {
      _starting = false;
    }
  }

  /// Opens [source] under [access] with [filter]; false when refused.
  Future<bool> _open(
    PositionSource source,
    LocationAccess access,
    Future<void> Function()? afterAccess,
    GpsFilter filter,
  ) async {
    if (!access.isGranted) {
      _refuse(access);
      return false;
    }
    await afterAccess?.call();
    _filter = filter;
    _sub = source
        .fixes() // the source's default 2 s, far under kMaxCreditGapSeconds
        .listen(_onFix, onError: _onError, onDone: _onDone);
    _issue = RunIssue.none;
    return true;
  }
}
