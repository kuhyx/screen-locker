/// The GPS activity state machine: idle, recording, paused, finished.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/pace_coach.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_math.dart';
import 'package:workout_app/services/run_phase.dart';

export 'package:workout_app/services/run_phase.dart';

/// Records one GPS activity from a [PositionSource].
///
/// Every activity is a run (one jump cap, one `Sport="Running"` TCX): the PC
/// credits every GPS activity with the same rule.
///
/// A pause ignores fixes and breaks the filter's segment, so the stretch
/// walked while paused and the first fix after it credit nothing. Moving time
/// is the PC's rule ([movingSeconds]) applied as fixes arrive, so the number
/// on screen is the number the PC will credit.
class RunRecorder extends ChangeNotifier {
  /// Creates a recorder; [sourceFor] builds the fix stream on [start].
  RunRecorder({
    required this.sourceFor,
    this.onKilometre,
    void Function(PaceCue cue)? onPaceCue,
  }) : coach = PaceCoach(onCue: onPaceCue);

  /// Builds the source for one recording.
  final PositionSource Function() sourceFor;

  /// Called with 1, 2, 3 ... as each whole kilometre is credited.
  final void Function(int km)? onKilometre;

  /// The pace target's state: current pace, band and cues.
  final PaceCoach coach;

  RunPhase _phase = RunPhase.idle;
  RunIssue _issue = RunIssue.none;
  GpsFilter? _filter;
  StreamSubscription<GpsFix>? _sub;
  bool _starting = false;
  int _moving = 0;
  int _km = 0;
  final _live = ValueNotifier<List<RunPoint>>(const []);
  final _seenVerdicts = <FixVerdict>{};

  /// The state machine's phase.
  RunPhase get phase => _phase;

  /// The current problem, or [RunIssue.none].
  RunIssue get issue => _issue;

  /// Accepted points so far, for the live map.
  ValueListenable<List<RunPoint>> get livePoints => _live;

  /// Credited moving time in seconds.
  int get seconds => _moving;

  /// Credited distance in metres.
  double get distanceM => _filter?.distanceM ?? 0;

  /// Sets the pace target ([seconds] per kilometre), or off with null.
  void setPaceTarget(int? seconds) {
    coach.setTarget(seconds);
    notifyListeners();
  }

  /// Folds an access check in while idle: a refusal becomes the issue, a
  /// grant clears it.
  void noteAccess(LocationAccess access) {
    if (_phase != RunPhase.idle) return;
    if (!access.isGranted) return _refuse(access);
    if (!_issue.isAccess) return;
    _issue = RunIssue.none;
    notifyListeners();
  }

  /// Asks for location access, runs [afterAccess] (where the caller starts the
  /// foreground service, which Android 14 only allows once access is held),
  /// then begins recording. False when access was refused or a start is
  /// already under way; [issue] says why.
  Future<bool> start({Future<void> Function()? afterAccess}) async {
    if (_phase != RunPhase.idle || _starting) return false;
    _starting = true;
    try {
      final source = sourceFor();
      final access = await source.requestAccess();
      if (!access.isGranted) {
        _refuse(access);
        return false;
      }
      await afterAccess?.call();
      _filter = GpsFilter();
      _sub = source
          .fixes() // the source's default 2 s, far under kMaxCreditGapSeconds
          .listen(_onFix, onError: _onError, onDone: _onDone);
      _issue = RunIssue.none;
      _phase = RunPhase.recording;
      SandboxLog.event('run started');
      notifyListeners();
      return true;
    } finally {
      _starting = false;
    }
  }

  /// Stops crediting until [resume].
  void pause() {
    if (_phase != RunPhase.recording) return;
    _filter!.breakSegment();
    _phase = RunPhase.paused;
    SandboxLog.event('run paused', {'m': distanceM});
    notifyListeners();
  }

  /// Continues after [pause].
  void resume() {
    if (_phase != RunPhase.paused) return;
    _phase = RunPhase.recording;
    coach.restartAt(_filter!.points.length);
    SandboxLog.event('run resumed', {'m': distanceM});
    notifyListeners();
  }

  /// Ends the recording and returns the track, or null when there were too
  /// few usable fixes (then [issue] is [RunIssue.tooShort]).
  Future<RunTrack?> finish() async {
    if (!_phase.isActive) return null;
    await _sub?.cancel();
    _sub = null;
    _phase = RunPhase.finished;
    final points = _filter!.points;
    _moving = movingSeconds(points);
    RunTrack? track;
    if (points.length < 2) {
      _issue = RunIssue.tooShort;
      log(
        'RunRecorder: finished with ${points.length} usable GPS fix(es) '
        '-- not enough for a track, so nothing is saved.',
        level: 1000,
      );
    } else {
      track = RunTrack.started(
        sport: RunSport.running,
        startedAt: points.first.time,
        points: points,
        totalSeconds: _moving,
        distanceM: _filter!.distanceM,
      );
    }
    SandboxLog.event('run finished', {
      'm': distanceM,
      'secs': _moving,
      'points': points.length,
      'saved': track != null,
    });
    notifyListeners();
    return track;
  }

  void _refuse(LocationAccess access) {
    _issue = RunIssue.forAccess(access);
    final fix = access == LocationAccess.serviceOff
        ? 'Switch location on'
        : 'Grant location to the app in system settings';
    log(
      'RunRecorder: not recording -- location access is ${access.name}. '
      '$fix and start again.',
      level: 1000,
    );
    notifyListeners();
  }

  void _onFix(GpsFix fix) {
    if (_phase != RunPhase.recording) return;
    final verdict = _filter!.add(fix);
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
    notifyListeners();
  }

  void _noteDropped(FixVerdict verdict) {
    if (verdict == FixVerdict.mocked) {
      _issue = RunIssue.mockedLocation;
      notifyListeners();
    }
    // Said once per kind and run: a bad tunnel would otherwise flood the log.
    if (!_seenVerdicts.add(verdict)) return;
    log(
      'RunRecorder: dropped a GPS fix (${verdict.name}); further drops of '
      'this kind are not logged. Mock fixes never count towards a run.',
      level: 900,
    );
  }

  void _onError(Object error, StackTrace stack) {
    _issue = RunIssue.streamError;
    log(
      'RunRecorder: the location stream failed ($error) -- fixes may have '
      'stopped; time and distance are not crediting until they resume.',
      level: 1000,
      error: error,
      stackTrace: stack,
    );
    notifyListeners();
  }

  void _onDone() {
    if (!_phase.isActive) return;
    log(
      'RunRecorder: the location stream ended while still recording; '
      'finish the run to save what was captured.',
      level: 900,
    );
    SandboxLog.event('run stream ended', {'m': distanceM});
  }

  @override
  void dispose() {
    unawaited(_sub?.cancel());
    _live.dispose();
    super.dispose();
  }
}
