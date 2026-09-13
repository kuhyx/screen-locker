/// What the foreground service needs to know about the running workout.
library;

import 'package:flutter/foundation.dart';

/// A complete picture of the workout, as the notification should show it.
///
/// Always sent whole, never as a delta. Android can restart the service isolate
/// independently of the UI, and a restarted isolate has no history to apply a
/// delta to — so the UI pushes the entire picture on every change instead.
@immutable
class BreakSnapshot {
  /// Creates a snapshot.
  const BreakSnapshot({
    required this.workoutType,
    required this.breakEndMs,
    required this.breakDurationSecs,
    required this.breakLabel,
    required this.breakForExIdx,
    required this.breakForSetIdx,
    required this.nextExIdx,
    required this.nextSetIdx,
    required this.nextExName,
    required this.nextSetNumber,
    required this.nextTotalSets,
    required this.nextReps,
    required this.nextWeight,
    required this.lastExIdx,
    required this.lastSetIdx,
    required this.setsRemaining,
    this.finished = false,
  });

  /// Rebuilds a snapshot from the map sent across the isolate boundary.
  ///
  /// Returns null rather than throwing: the payload crosses a platform channel,
  /// and a malformed one must leave the notification as it was instead of
  /// taking down the service isolate.
  static BreakSnapshot? tryFromMap(Map<Object?, Object?> map) {
    int? i(String k) => map[k] is int ? map[k]! as int : null;
    final workoutType = map['workoutType'];
    if (workoutType is! String) return null;
    final nextExName = map['nextExName'];
    if (nextExName is! String) return null;
    final breakLabel = map['breakLabel'];
    if (breakLabel is! String) return null;
    final weight = map['nextWeight'];
    if (weight is! num) return null;
    final keys = [
      'breakEndMs',
      'breakDurationSecs',
      'breakForExIdx',
      'breakForSetIdx',
      'nextExIdx',
      'nextSetIdx',
      'nextSetNumber',
      'nextTotalSets',
      'nextReps',
      'lastExIdx',
      'lastSetIdx',
      'setsRemaining',
    ];
    for (final k in keys) {
      if (i(k) == null) return null;
    }
    return BreakSnapshot(
      workoutType: workoutType,
      breakEndMs: i('breakEndMs')!,
      breakDurationSecs: i('breakDurationSecs')!,
      breakLabel: breakLabel,
      breakForExIdx: i('breakForExIdx')!,
      breakForSetIdx: i('breakForSetIdx')!,
      nextExIdx: i('nextExIdx')!,
      nextSetIdx: i('nextSetIdx')!,
      nextExName: nextExName,
      nextSetNumber: i('nextSetNumber')!,
      nextTotalSets: i('nextTotalSets')!,
      nextReps: i('nextReps')!,
      nextWeight: weight.toDouble(),
      lastExIdx: i('lastExIdx')!,
      lastSetIdx: i('lastSetIdx')!,
      setsRemaining: i('setsRemaining')!,
      finished: map['finished'] == true,
    );
  }

  /// 'A' or 'B'.
  final String workoutType;

  /// Wall-clock deadline of the running rest, or 0 when none is running.
  final int breakEndMs;

  /// Full length of the running rest, for the countdown's denominator.
  final int breakDurationSecs;

  /// Human label of the running rest, e.g. 'Rest (3 min — well done!)'.
  final String breakLabel;

  /// Exercise the running rest belongs to, or -1.
  final int breakForExIdx;

  /// Set the running rest belongs to; -1 means a warmup rest.
  final int breakForSetIdx;

  /// Exercise the `Done` button would record, or -1 when the workout is over.
  final int nextExIdx;

  /// Set the `Done` button would record, or -1 when the workout is over.
  final int nextSetIdx;

  /// Display name of the next exercise.
  final String nextExName;

  /// 1-based number of the next set, for 'set 3/5'.
  final int nextSetNumber;

  /// How many sets that exercise has, for 'set 3/5'.
  final int nextTotalSets;

  /// Target reps of the next set.
  final int nextReps;

  /// Working weight of the next set, in kg.
  final double nextWeight;

  /// Exercise the `− 1 rep` button would decrement, or -1.
  final int lastExIdx;

  /// Set the `− 1 rep` button would decrement, or -1.
  final int lastSetIdx;

  /// Sets still untapped across the whole workout.
  final int setsRemaining;

  /// True once the workout has been finished and saved.
  final bool finished;

  /// True while a rest period is recorded as running.
  bool get hasBreak => breakEndMs > 0;

  /// True when there is a set left for `Done` to record.
  bool get hasNextSet => nextExIdx >= 0 && nextSetIdx >= 0;

  /// Flattens this snapshot for `sendDataToTask`, which takes primitives only.
  Map<String, Object?> toMap() => {
    'workoutType': workoutType,
    'breakEndMs': breakEndMs,
    'breakDurationSecs': breakDurationSecs,
    'breakLabel': breakLabel,
    'breakForExIdx': breakForExIdx,
    'breakForSetIdx': breakForSetIdx,
    'nextExIdx': nextExIdx,
    'nextSetIdx': nextSetIdx,
    'nextExName': nextExName,
    'nextSetNumber': nextSetNumber,
    'nextTotalSets': nextTotalSets,
    'nextReps': nextReps,
    'nextWeight': nextWeight,
    'lastExIdx': lastExIdx,
    'lastSetIdx': lastSetIdx,
    'setsRemaining': setsRemaining,
    'finished': finished,
  };

  /// Returns a copy with the listed fields replaced.
  BreakSnapshot copyWith({
    int? breakEndMs,
    int? breakDurationSecs,
    String? breakLabel,
    int? setsRemaining,
    bool? finished,
  }) => BreakSnapshot(
    workoutType: workoutType,
    breakEndMs: breakEndMs ?? this.breakEndMs,
    breakDurationSecs: breakDurationSecs ?? this.breakDurationSecs,
    breakLabel: breakLabel ?? this.breakLabel,
    breakForExIdx: breakForExIdx,
    breakForSetIdx: breakForSetIdx,
    nextExIdx: nextExIdx,
    nextSetIdx: nextSetIdx,
    nextExName: nextExName,
    nextSetNumber: nextSetNumber,
    nextTotalSets: nextTotalSets,
    nextReps: nextReps,
    nextWeight: nextWeight,
    lastExIdx: lastExIdx,
    lastSetIdx: lastSetIdx,
    setsRemaining: setsRemaining ?? this.setsRemaining,
    finished: finished ?? this.finished,
  );
}
