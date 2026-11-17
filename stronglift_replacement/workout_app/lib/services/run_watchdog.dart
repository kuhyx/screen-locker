/// Watches a run for the signs that it should end: suggests finishing, and
/// ends it after 5 hours of wall clock.
///
/// It never finishes a run itself: [onSuggest] is advice, [onAutoEnd] tells
/// the host to call `finish()`. Checks run off a periodic [Timer] and the
/// injected [clock], not only when a fix arrives, so a silent GPS is noticed.
library;

import 'dart:async';

import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_math.dart';
import 'package:workout_app/services/run_phase.dart';

/// The suggest-finish thresholds; the defaults are the agreed rules, the
/// sandbox and the tests shrink them.
class RunLimits {
  /// Creates limits.
  const RunLimits({
    this.stationaryWindow = const Duration(minutes: 10),
    this.stationaryMinM = 50,
    this.vehicleSpeedMps = 25 / 3.6,
    this.vehicleWindow = const Duration(seconds: 60),
    this.noFixAfter = const Duration(minutes: 5),
    this.tick = const Duration(seconds: 5),
  });

  /// The progress window for [RunSuggestion.stationary].
  final Duration stationaryWindow;

  /// Credited metres a [stationaryWindow] needs to stay quiet.
  final double stationaryMinM;

  /// Speed above which a stretch looks like a vehicle, in metres per second.
  final double vehicleSpeedMps;

  /// How long that speed must hold.
  final Duration vehicleWindow;

  /// How long without a usable fix before [RunSuggestion.gpsLost].
  final Duration noFixAfter;

  /// How often the timer checks.
  final Duration tick;
}

/// The suggest-finish and auto-end rules of one run.
class RunWatchdog {
  /// Creates a watchdog with the agreed rules unless [limits] or
  /// [autoEndAfter] say otherwise.
  RunWatchdog({
    required this.clock,
    required this.onSuggest,
    required this.onAutoEnd,
    this.autoEndAfter = const Duration(hours: 5),
    this.limits = const RunLimits(),
  });

  /// The wall clock.
  final DateTime Function() clock;

  /// Hears each suggestion to finish.
  final void Function(RunSuggestion why) onSuggest;

  /// Hears the auto end, once; the host then finishes the run.
  final void Function() onAutoEnd;

  /// Wall-clock run length (pauses and phone-off time included) that ends it.
  final Duration autoEndAfter;

  /// The suggest-finish thresholds.
  final RunLimits limits;

  Timer? _timer;
  DateTime? _startedAt;
  bool _paused = false;
  bool _ended = false;
  late DateTime _lastFixAt;
  late DateTime _anchorAt;
  double _anchorM = 0;
  double _distanceM = 0;
  bool _lostFired = false;
  GpsFix? _prev;
  DateTime? _fastSince;
  bool _fastFired = false;

  /// Starts watching a run that began at [startedAt].
  void begin(DateTime startedAt) {
    _startedAt = startedAt.toUtc();
    _ended = false;
    _paused = false;
    _distanceM = 0;
    _rebase();
    _timer?.cancel();
    _timer = Timer.periodic(limits.tick, (_) => check());
  }

  /// Starts watching a run restored from a checkpoint: advises finishing, or
  /// ends it at once when 5 hours have already passed.
  void restored(
    DateTime startedAt, {
    required bool paused,
    required double distanceM,
  }) {
    begin(startedAt);
    _paused = paused;
    _distanceM = distanceM;
    _anchorM = distanceM;
    if (_expired()) {
      check();
    } else {
      onSuggest(RunSuggestion.restored);
    }
  }

  /// Stops all checks (finish or dispose). Safe to call twice.
  void stop() {
    _timer?.cancel();
    _timer = null;
    _startedAt = null;
  }

  /// A pause: nothing fires until [resume].
  void pause() => _paused = true;

  /// After a pause the windows start afresh, so paused time never reads as
  /// standing still or a lost signal.
  void resume() {
    _paused = false;
    _rebase();
  }

  /// Folds in one raw fix and the filter's [verdict] on it.
  ///
  /// Too-fast fixes count: a vehicle never yields an accepted fix, the
  /// filter drops it as a jump, so speed is read off raw consecutive fixes.
  void onFix(GpsFix fix, FixVerdict verdict, double distanceM) {
    if (verdict != FixVerdict.accepted && verdict != FixVerdict.tooFast) {
      return;
    }
    _distanceM = distanceM;
    _lastFixAt = clock();
    _lostFired = false;
    _readSpeed(fix);
    check();
  }

  void _readSpeed(GpsFix fix) {
    final prev = _prev;
    if (prev == null) {
      _prev = fix;
      return;
    }
    final dt = fix.time.difference(prev.time).inSeconds;
    if (dt <= 0) return; // a same-second fix says nothing about speed
    _prev = fix;
    final speed =
        haversineM(prev.latitude, prev.longitude, fix.latitude, fix.longitude) /
        dt;
    if (speed <= limits.vehicleSpeedMps) {
      _fastSince = null;
      _fastFired = false;
      return;
    }
    _fastSince ??= fix.time;
    if (!_fastFired &&
        fix.time.difference(_fastSince!) >= limits.vehicleWindow) {
      _fastFired = true;
      onSuggest(RunSuggestion.vehicleSpeed);
    }
  }

  /// Runs every rule against the clock; the timer calls this every [tick].
  void check() {
    final started = _startedAt;
    if (started == null || _ended) return;
    if (_expired()) {
      _ended = true;
      _timer?.cancel();
      onAutoEnd();
      return;
    }
    if (_paused) return;
    final now = clock();
    if (!_lostFired && now.difference(_lastFixAt) >= limits.noFixAfter) {
      _lostFired = true;
      onSuggest(RunSuggestion.gpsLost);
    }
    if (now.difference(_anchorAt) >= limits.stationaryWindow) {
      final progress = _distanceM - _anchorM;
      _anchorAt = now;
      _anchorM = _distanceM;
      if (progress < limits.stationaryMinM) onSuggest(RunSuggestion.stationary);
    }
  }

  bool _expired() => !_ended && clock().difference(_startedAt!) >= autoEndAfter;

  void _rebase() {
    final now = clock();
    _lastFixAt = now;
    _anchorAt = now;
    _anchorM = _distanceM;
    _lostFired = false;
    _prev = null;
    _fastSince = null;
    _fastFired = false;
  }
}
