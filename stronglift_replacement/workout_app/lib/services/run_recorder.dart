/// The GPS activity state machine: idle, recording, paused, finished.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/pace_coach.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_math.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_recorder_log.dart';
import 'package:workout_app/services/run_watchdog.dart';

export 'package:workout_app/services/run_phase.dart';
export 'package:workout_app/services/run_watchdog.dart' show RunLimits;

part 'run_recorder_fixes.dart';
part 'run_recorder_persist.dart';

/// Records one GPS activity from a [PositionSource].
///
/// Every activity is a run (one jump cap, one `Sport="Running"` TCX): the PC
/// credits every GPS activity with the same rule.
///
/// A pause ignores fixes and breaks the filter's segment, so the stretch
/// walked while paused and the first fix after it credit nothing. Moving time
/// is [movingSeconds] applied as fixes arrive: an estimate that mirrors the
/// PC's bounds per pair of fixes, not its 10 s windows (see `run_math.dart`).
///
/// The run survives a dead process: [onCheckpoint] hands the host a
/// [RunCheckpoint] after every accepted fix and on pause or resume, and
/// `restore` (see `run_recorder_persist.dart`) rebuilds the recording from
/// one. A gap (dead phone, GPS dropout) is bridged by a straight line (see
/// `run_gap_bridge.dart`). A [RunWatchdog] suggests finishing and ends the
/// run after 5 h of wall clock.
class RunRecorder extends ChangeNotifier {
  /// Creates a recorder; [sourceFor] builds the fix stream on [start].
  ///
  /// [clock] is the wall-clock seam; [autoEndAfter] and [limits] default to
  /// the agreed rules and are shrunk by the sandbox and the tests.
  RunRecorder({
    required this.sourceFor,
    this.onKilometre,
    void Function(PaceCue cue)? onPaceCue,
    this.onSuggestFinish,
    this.onAutoEnd,
    this.onCheckpoint,
    DateTime Function() clock = DateTime.now,
    Duration autoEndAfter = const Duration(hours: 5),
    RunLimits limits = const RunLimits(),
  }) : _clock = clock,
       coach = PaceCoach(onCue: onPaceCue) {
    _watch = RunWatchdog(
      clock: clock,
      onSuggest: (why) => onSuggestFinish?.call(why),
      onAutoEnd: () => onAutoEnd?.call(),
      autoEndAfter: autoEndAfter,
      limits: limits,
    );
  }

  /// Builds the source for one recording.
  final PositionSource Function() sourceFor;

  /// Called with 1, 2, 3 ... as each whole kilometre is credited.
  final void Function(int km)? onKilometre;

  /// Advice to finish the run (never ends it).
  final void Function(RunSuggestion why)? onSuggestFinish;

  /// Called once after 5 h of wall clock; the host then calls [finish].
  final void Function()? onAutoEnd;

  /// Hears a fresh checkpoint after every accepted fix, on start, pause and
  /// resume: the host stores it.
  final void Function(RunCheckpoint checkpoint)? onCheckpoint;

  /// The pace target's state: current pace, band and cues.
  final PaceCoach coach;

  final DateTime Function() _clock;
  late final RunWatchdog _watch;
  RunPhase _phase = RunPhase.idle;
  RunIssue _issue = RunIssue.none;
  GpsFilter? _filter;
  StreamSubscription<GpsFix>? _sub;
  late DateTime _startedAt;
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
      if (!await _open(source, access, afterAccess, GpsFilter())) {
        return false;
      }
      _startedAt = _clock().toUtc();
      _phase = RunPhase.recording;
      _watch.begin(_startedAt);
      SandboxLog.event('run started');
      _announce();
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
    _watch.pause();
    SandboxLog.event('run paused', {'m': distanceM});
    _announce();
  }

  /// Continues after [pause].
  void resume() {
    if (_phase != RunPhase.paused) return;
    _phase = RunPhase.recording;
    coach.restartAt(_filter!.points.length);
    _watch.resume();
    SandboxLog.event('run resumed', {'m': distanceM});
    _announce();
  }

  /// Ends the recording and returns the track, or null when there were too
  /// few usable fixes (then [issue] is [RunIssue.tooShort]).
  Future<RunTrack?> finish() async {
    if (!_phase.isActive) return null;
    _watch.stop();
    await _sub?.cancel();
    _sub = null;
    _phase = RunPhase.finished;
    final points = _filter!.points;
    _moving = movingSeconds(points);
    RunTrack? track;
    if (points.length < 2) {
      _issue = RunIssue.tooShort;
      logTooShort(points.length);
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

  /// [notifyListeners] for the `part` files' extensions, which may not call
  /// a protected member themselves.
  void _changed() => notifyListeners();

  /// Tells listeners and hands the host a fresh checkpoint.
  void _announce() {
    notifyListeners();
    final c = onCheckpoint == null ? null : checkpoint();
    if (c != null) onCheckpoint!(c);
  }

  void _refuse(LocationAccess access) {
    _issue = RunIssue.forAccess(access);
    logRefused(access);
    notifyListeners();
  }

  @override
  void dispose() {
    _watch.stop();
    unawaited(_sub?.cancel());
    _live.dispose();
    super.dispose();
  }
}
