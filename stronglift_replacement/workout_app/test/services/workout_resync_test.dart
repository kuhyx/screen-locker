/// A failed workout push is retried by itself until a tick gets through.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/workout_resync.dart';
import 'package:workout_app/services/workout_sync_service.dart';

/// A scheduler that keeps the callbacks instead of starting real timers.
class _Clock {
  final pending = <void Function()>[];
  final delays = <Duration>[];

  Timer call(Duration after, void Function() fire) {
    delays.add(after);
    pending.add(fire);
    return Timer(Duration.zero, () {})..cancel();
  }

  Future<void> fireNext() async {
    pending.removeAt(0)();
    await Future<void>.delayed(Duration.zero);
  }
}

const _failed = PushResult(pushed: false, reason: 'push failed: offline');
const _ok = PushResult(pushed: true, reason: 'synced');

void main() {
  test('a failed push arms a retry that runs a sync tick', () async {
    final clock = _Clock();
    var ticks = 0;
    WorkoutResync(
      syncNow: () async {
        ticks++;
        return _ok;
      },
      scheduler: clock.call,
    ).note(_failed);

    expect(clock.delays, [kWorkoutResyncAfter]);
    await clock.fireNext();

    expect(ticks, 1);
    expect(clock.pending, isEmpty);
  });

  test('a retry that fails again arms the next one', () async {
    final clock = _Clock();
    WorkoutResync(
      syncNow: () async => _failed,
      scheduler: clock.call,
    ).note(_failed);

    await clock.fireNext();

    expect(clock.pending, hasLength(1));
  });

  test('no retry while sync is not set up, nor after a success', () {
    final clock = _Clock();
    WorkoutResync(syncNow: () async => _ok, scheduler: clock.call)
      ..note(const PushResult(pushed: false, reason: kSyncNotConfigured))
      ..note(_ok);

    expect(clock.pending, isEmpty);
  });

  test('two failures arm one retry, not two', () {
    final clock = _Clock();
    WorkoutResync(syncNow: () async => _ok, scheduler: clock.call)
      ..note(_failed)
      ..note(_failed);

    expect(clock.pending, hasLength(1));
  });

  test('syncNow runs a tick at once and folds its result in', () async {
    final clock = _Clock();
    await WorkoutResync(
      syncNow: () async => _failed,
      scheduler: clock.call,
    ).syncNow();

    expect(clock.pending, hasLength(1));
  });
}
