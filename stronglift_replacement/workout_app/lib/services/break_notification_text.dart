/// The words on the workout's ongoing status-bar notification.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_clock.dart';

/// Rendered notification copy: what Android shows collapsed, and expanded.
@immutable
class BreakNotificationCopy {
  /// Creates a rendered title/body pair.
  const BreakNotificationCopy(this.title, this.body);

  /// Line one. Android shows this even when the notification is collapsed, so
  /// the countdown lives here rather than in the body.
  final String title;

  /// Lines two and three: which exercise, which set, how many reps at what
  /// weight. Only visible when the notification is expanded.
  final String body;

  @override
  bool operator ==(Object other) =>
      other is BreakNotificationCopy &&
      other.title == title &&
      other.body == body;

  @override
  int get hashCode => Object.hash(title, body);

  @override
  String toString() => 'BreakNotificationCopy($title | $body)';
}

/// Turns a [BreakSnapshot] into the text on the notification.
///
/// Pure by design: this is the part that changes every second, so it has to be
/// cheap to compare (the service only redraws when the text actually changed)
/// and testable without a device.
abstract final class BreakNotificationText {
  /// Renders the notification for [snapshot] as of [now].
  static BreakNotificationCopy render(BreakSnapshot snapshot, DateTime now) {
    if (snapshot.finished) {
      return const BreakNotificationCopy(
        'Workout complete',
        'Open the app to save it.',
      );
    }
    return BreakNotificationCopy(
      _title(snapshot, now),
      _body(snapshot),
    );
  }

  static String _title(BreakSnapshot s, DateTime now) {
    final prefix = 'Workout ${s.workoutType}';
    if (!s.hasBreak) {
      return '$prefix · lift';
    }
    final clock = BreakClock(
      endTime: DateTime.fromMillisecondsSinceEpoch(s.breakEndMs),
      durationSecs: s.breakDurationSecs,
    );
    final remaining = clock.remainingSecsAt(now);
    if (remaining <= 0) return '$prefix · break over';
    return '$prefix · break ${formatMmSs(remaining)}';
  }

  static String _body(BreakSnapshot s) {
    if (!s.hasNextSet) return 'Every set is done — finish the workout.';
    return 'Next: ${s.nextExName} — set ${s.nextSetNumber}/${s.nextTotalSets}\n'
        '${s.nextReps} reps @ ${formatWeight(s.nextWeight)} kg';
  }

  /// Formats [totalSecs] as `m:ss`, e.g. 107 -> `1:47`.
  static String formatMmSs(int totalSecs) {
    final m = totalSecs ~/ 60;
    final s = (totalSecs % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  /// Formats [kg] without a pointless trailing zero: 40.0 -> `40`.
  static String formatWeight(double kg) {
    final oneDp = kg.toStringAsFixed(1);
    return oneDp.endsWith('.0') ? oneDp.substring(0, oneDp.length - 2) : oneDp;
  }
}
