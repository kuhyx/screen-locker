/// Retries a failed workout push by itself, until a sync tick gets through.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/services/workout_sync_service.dart';

/// How long after a failed tick the next one runs while the app is open.
const Duration kWorkoutResyncAfter = Duration(minutes: 5);

/// Re-runs [WorkoutSyncService.syncNow] after a failure.
///
/// A tick needs no record to re-send: the push wrote its record to the local
/// log first, and every tick pushes that log. So a retry is just a tick.
/// The app also ticks on every home-screen open and on resume; this covers
/// the phone that stays open on the summary with the network down.
class WorkoutResync {
  /// Creates a retrier; the arguments are test seams.
  WorkoutResync({
    Future<PushResult> Function()? syncNow,
    Timer Function(Duration, void Function())? scheduler,
  }) : _syncNow = syncNow ?? WorkoutSyncService().syncNow,
       _schedule = scheduler ?? Timer.new;

  /// The app-wide retrier.
  static final WorkoutResync instance = WorkoutResync();

  final Future<PushResult> Function() _syncNow;
  final Timer Function(Duration, void Function()) _schedule;
  Timer? _retry;
  bool _armed = false;

  /// Folds a tick's [result] in: a failure arms one retry, a success or a
  /// device with no sync set up (nothing a retry could fix) disarms it.
  void note(PushResult result) {
    if (result.pushed || result.reason == kSyncNotConfigured) {
      _retry?.cancel();
      _armed = false;
      return;
    }
    if (_armed) return;
    _armed = true;
    log(
      'WorkoutResync: ${result.reason}; trying again in '
      '${kWorkoutResyncAfter.inMinutes} min',
      level: 900,
    );
    _retry = _schedule(kWorkoutResyncAfter, () {
      _armed = false;
      unawaited(syncNow());
    });
  }

  /// Runs a tick now (e.g. the app came back to the foreground).
  Future<void> syncNow() async => note(await _syncNow());
}
