/// The GPS run/walk state machine: idle, recording, paused, finished.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/services/run_math.dart';

/// Where a recording stands.
enum RunPhase {
  /// Nothing recorded yet; the sport can still be chosen.
  idle,

  /// Fixes are being kept and credited.
  recording,

  /// Fixes are ignored; nothing is credited until [RunRecorder.resume].
  paused,

  /// Over; [RunRecorder.finish] has returned the track.
  finished,
}

/// What is wrong with the recording right now (shown as an icon, logged).
enum RunIssue {
  /// Nothing.
  none,

  /// Location permission refused; asking again may work.
  denied,

  /// Location permission refused for good; only system settings can fix it.
  deniedForever,

  /// The device's location switch is off.
  serviceOff,

  /// The newest fix came from a mock-location provider and was dropped.
  mockedLocation,

  /// The location stream reported an error.
  streamError,

  /// Finished with too few usable fixes to make a track; nothing was saved.
  tooShort,
}

/// Records one run or walk from a [PositionSource].
///
/// A pause ignores fixes and breaks the filter's segment, so the stretch
/// walked while paused and the first fix after it credit nothing. Moving time
/// is the PC's rule ([movingSeconds]) applied as fixes arrive, so the number
/// on screen is the number the PC will credit.
class RunRecorder extends ChangeNotifier {
  /// Creates a recorder; [sourceFor] builds the fix stream for the chosen
  /// sport when [start] is called (the sandbox's replay speed follows it).
  RunRecorder({required this.sourceFor, this.onKilometre});

  /// Builds the source for one recording.
  final PositionSource Function(RunSport sport) sourceFor;

  /// Called with 1, 2, 3 ... as each whole kilometre is credited.
  final void Function(int km)? onKilometre;

  RunSport _sport = RunSport.running;
  RunPhase _phase = RunPhase.idle;
  RunIssue _issue = RunIssue.none;
  GpsFilter? _filter;
  StreamSubscription<GpsFix>? _sub;
  bool _starting = false;
  int _moving = 0;
  int _km = 0;
  final _live = ValueNotifier<List<RunPoint>>(const []);
  final _seenVerdicts = <FixVerdict>{};

  /// Running or walking.
  RunSport get sport => _sport;

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

  /// Average pace in seconds per km, or null while the run is too short.
  double? get pace => paceSecPerKm(_moving, distanceM);

  /// Picks the sport; only possible while [RunPhase.idle].
  bool selectSport(RunSport sport) {
    if (_phase != RunPhase.idle) return false;
    _sport = sport;
    notifyListeners();
    return true;
  }

  /// Asks for location access, runs [afterAccess] (where the caller starts the
  /// foreground service, which Android 14 only allows once access is held),
  /// then begins recording. False when access was refused or a start is
  /// already under way; [issue] says why.
  Future<bool> start({Future<void> Function()? afterAccess}) async {
    if (_phase != RunPhase.idle || _starting) return false;
    _starting = true;
    try {
      final source = sourceFor(_sport);
      final access = await source.requestAccess();
      if (!access.isGranted) {
        _refuse(access);
        return false;
      }
      await afterAccess?.call();
      _filter = GpsFilter(sport: _sport);
      _sub = source
          .fixes() // the source's default 2 s, far under kMaxCreditGapSeconds
          .listen(_onFix, onError: _onError, onDone: _onDone);
      _issue = RunIssue.none;
      _phase = RunPhase.recording;
      SandboxLog.event('run started', {'sport': _sport.tcxName});
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
    SandboxLog.event('run paused', {'km': formatKm(distanceM)});
    notifyListeners();
  }

  /// Continues after [pause].
  void resume() {
    if (_phase != RunPhase.paused) return;
    _phase = RunPhase.recording;
    SandboxLog.event('run resumed', {'km': formatKm(distanceM)});
    notifyListeners();
  }

  /// Ends the recording and returns the track, or null when there were too
  /// few usable fixes (then [issue] is [RunIssue.tooShort]).
  Future<RunTrack?> finish() async {
    if (_phase != RunPhase.recording && _phase != RunPhase.paused) return null;
    await _sub?.cancel();
    _sub = null;
    _phase = RunPhase.finished;
    final points = _filter!.points;
    _moving = movingSeconds(points, _sport);
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
        sport: _sport,
        startedAt: points.first.time,
        points: points,
        totalSeconds: _moving,
        distanceM: _filter!.distanceM,
      );
    }
    SandboxLog.event('run finished', {
      'km': formatKm(distanceM),
      'secs': _moving,
      'points': points.length,
      'saved': track != null,
    });
    notifyListeners();
    return track;
  }

  void _refuse(LocationAccess access) {
    _issue = switch (access) {
      LocationAccess.deniedForever => RunIssue.deniedForever,
      LocationAccess.serviceOff => RunIssue.serviceOff,
      _ => RunIssue.denied,
    };
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
        isMovingStep(points[n - 2], points[n - 1], maxSpeedMps(_sport))) {
      _moving += points[n - 1].time.difference(points[n - 2].time).inSeconds;
    }
    _live.value = points;
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
    if (_phase != RunPhase.recording && _phase != RunPhase.paused) return;
    log(
      'RunRecorder: the location stream ended while still recording; '
      'finish the run to save what was captured.',
      level: 900,
    );
    SandboxLog.event('run stream ended', {'km': formatKm(distanceM)});
  }

  @override
  void dispose() {
    unawaited(_sub?.cancel());
    _live.dispose();
    super.dispose();
  }
}
