/// Wall-clock arithmetic for a rest period between sets.
library;

import 'package:flutter/foundation.dart';

/// An immutable rest period, described by when it *ends* rather than by how
/// many ticks are left.
///
/// The break countdown used to be a plain `int` decremented once per
/// `Timer.periodic` tick. Android throttles — and in Doze suspends — timers in
/// a backgrounded isolate, so that counter stalled, never reached zero, and the
/// break-end cue never fired. Deriving the remaining time from a stored
/// deadline makes a stalled timer merely *stale*: the next tick, whenever it
/// lands, reports the truth.
@immutable
class BreakClock {
  /// Creates a clock for a break of [durationSecs] ending at [endTime].
  const BreakClock({required this.endTime, required this.durationSecs});

  /// Creates a clock for a break of [durationSecs] starting at [start].
  factory BreakClock.startingAt(DateTime start, int durationSecs) => BreakClock(
    endTime: start.add(Duration(seconds: durationSecs)),
    durationSecs: durationSecs,
  );

  /// When the rest period is over.
  final DateTime endTime;

  /// The rest period's full length in seconds, for the progress bar.
  final int durationSecs;

  /// When the rest period began.
  DateTime get startTime => endTime.subtract(Duration(seconds: durationSecs));

  /// Whole seconds left at [now], rounded up and floored at zero.
  ///
  /// Rounded up so a break of 180 s reads "180" for its whole first second,
  /// matching what the decrementing counter used to show.
  int remainingSecsAt(DateTime now) {
    final us = endTime.difference(now).inMicroseconds;
    if (us <= 0) return 0;
    return (us + Duration.microsecondsPerSecond - 1) ~/
        Duration.microsecondsPerSecond;
  }

  /// True once [now] has reached [endTime].
  bool expiredAt(DateTime now) => !now.isBefore(endTime);

  /// Whole seconds since the break ended; zero while it is still running.
  int secondsOverdueAt(DateTime now) {
    final overdue = now.difference(endTime).inSeconds;
    return overdue > 0 ? overdue : 0;
  }

  /// Returns this break re-cut to [secs], keeping the moment it started.
  ///
  /// This is the 3-min ↔ 5-min switch that happens when the user decrements
  /// reps on the set that earned the rest: the clock does not restart, it just
  /// ends sooner or later than it was going to.
  BreakClock withDuration(int secs) => BreakClock.startingAt(startTime, secs);

  @override
  bool operator ==(Object other) =>
      other is BreakClock &&
      other.endTime == endTime &&
      other.durationSecs == durationSecs;

  @override
  int get hashCode => Object.hash(endTime, durationSecs);

  @override
  String toString() => 'BreakClock($endTime, ${durationSecs}s)';
}
