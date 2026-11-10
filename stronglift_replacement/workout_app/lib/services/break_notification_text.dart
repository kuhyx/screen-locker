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
  ///
  /// Symbols and numbers only (textgate). The same glyphs as the alert
  /// notifications in break_service_port_flutter.dart: [doneGlyph] for a
  /// finished workout, [breakOverGlyph] when the rest is up.
  static BreakNotificationCopy render(BreakSnapshot snapshot, DateTime now) {
    if (snapshot.finished) {
      // Was "Workout complete" / "Open the app to save it."
      return const BreakNotificationCopy(doneGlyph, '');
    }
    return BreakNotificationCopy(_title(snapshot, now), _body(snapshot));
  }

  /// Finished workout (all sets, or the workout itself).
  static const doneGlyph = '✅';

  /// The rest period is over.
  static const breakOverGlyph = '⏰';

  /// A rest period is counting down.
  static const breakGlyph = '⏱';

  /// Lifting: no rest running.
  static const liftGlyph = '🏋';

  /// Name of every notification channel: the app's proper noun only
  /// (textgate settled decision 4), the same as `MaterialApp.title`.
  static const channelName = 'Workout Tracker';

  // Was "Workout A · lift" / "Workout A · break over" / "Workout A · break
  // 1:47".
  static String _title(BreakSnapshot s, DateTime now) {
    final prefix = '$liftGlyph ${s.workoutType}';
    if (!s.hasBreak) {
      return prefix;
    }
    final clock = BreakClock(
      endTime: DateTime.fromMillisecondsSinceEpoch(s.breakEndMs),
      durationSecs: s.breakDurationSecs,
    );
    final remaining = clock.remainingSecsAt(now);
    if (remaining <= 0) return '$prefix · $breakOverGlyph';
    return '$prefix · $breakGlyph ${formatMmSs(remaining)}';
  }

  // Was "Every set is done — finish the workout." / "Next: Squat — set 3/5
  // \n5 reps @ 40 kg". The exercise name is user content.
  static String _body(BreakSnapshot s) {
    if (!s.hasNextSet) return doneGlyph;
    return '→ ${s.nextExName}  ${s.nextSetNumber}/${s.nextTotalSets}\n'
        '${s.nextReps} × ${formatWeight(s.nextWeight)} kg';
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
