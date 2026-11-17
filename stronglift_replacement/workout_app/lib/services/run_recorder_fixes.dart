// What the recorder does with each fix, error and end of the stream: a `part`
// file so the state machine itself stays short.
part of 'run_recorder.dart';

extension _FixHandling on RunRecorder {
  void _onFix(GpsFix fix) {
    if (_phase != RunPhase.recording) return;
    final verdict = _filter!.add(fix);
    _watch.onFix(fix, verdict, distanceM);
    if (verdict != FixVerdict.accepted) {
      _noteDropped(verdict);
      return;
    }
    _issue = RunIssue.none;
    final points = _filter!.points;
    final n = points.length;
    if (n >= 2 &&
        isMovingStep(points[n - 2], points[n - 1], kRunningMaxSpeedMps)) {
      _moving += points[n - 1].time.difference(points[n - 2].time).inSeconds;
    }
    _live.value = points;
    coach.update(points);
    while (distanceM ~/ 1000 > _km) {
      _km++;
      SandboxLog.event('run km', {'km': _km, 'secs': _moving});
      onKilometre?.call(_km);
    }
    _announce();
  }

  void _noteDropped(FixVerdict verdict) {
    if (verdict == FixVerdict.mocked) {
      _issue = RunIssue.mockedLocation;
      _changed();
    }
    // Said once per kind and run: a bad tunnel would otherwise flood the log.
    if (_seenVerdicts.add(verdict)) logDropped(verdict);
  }

  void _onError(Object error, StackTrace stack) {
    _issue = RunIssue.streamError;
    logStreamError(error, stack);
    _changed();
  }

  void _onDone() {
    if (!_phase.isActive) return;
    logStreamEnded();
    SandboxLog.event('run stream ended', {'m': distanceM});
  }
}
