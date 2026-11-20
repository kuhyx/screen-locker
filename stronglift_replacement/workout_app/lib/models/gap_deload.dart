/// The gap deload: how far a training break cuts an exercise's target.
///
/// Applied when the workout loads, not when it finishes. The old rule lived
/// in `applyProgression` and could never fire: finishing saves the session
/// first, so "days since the last workout" was always 0. It also only ever
/// took one step, so a two-week break started from the pre-gap max.
///
/// Pure on purpose: the storage layer decides *whether* an exercise is due
/// (stamp, history) and these functions decide *how much*.
library;

import 'package:workout_app/models/progression.dart';

/// Shortest break, in calendar days, that costs a step.
const int kGapDeloadMinDays = 7;

/// Every further week of break costs one more step.
const int kGapDeloadDaysPerStep = 7;

/// The most a gap deload may take off the pre-gap weight (or reps, in reps
/// mode): a hard cap, however long the break.
const double kGapDeloadMaxLoss = 0.4;

/// `progression_events.kind` of a deload a training gap caused at load.
const String kGapDeloadKind = 'gap_deload';

/// `progression_events.kind` of the one-time repair of existing data.
const String kBackfillDeloadKind = 'backfill_deload';

/// Calendar days from [from] to [to]: 23:00 to 01:00 next day is one day.
///
/// Built from UTC dates so a DST change inside the gap cannot shave an hour
/// off and turn 7 days into 6.
int gapCalendarDays(DateTime from, DateTime to) => DateTime.utc(
  to.year,
  to.month,
  to.day,
).difference(DateTime.utc(from.year, from.month, from.day)).inDays;

/// Regression steps a break of [gapDays] calendar days costs: under 7 none,
/// 7-13 one, 14-20 two, then one more per extra week.
int gapDeloadSteps(int gapDays) => gapDays < kGapDeloadMinDays
    ? 0
    : 1 + (gapDays - kGapDeloadMinDays) ~/ kGapDeloadDaysPerStep;

/// [s]'s target after [steps] regression steps, each one
/// [targetAfterFailure], stopping before any step that would take more than
/// [kGapDeloadMaxLoss] off [s]'s weight (or, in reps mode, its reps).
///
/// A step that alone breaks the cap is not taken: 5 kg -> 2.5 kg is a 50%
/// loss, so a 5 kg exercise keeps 5 kg. Double progression caps on weight
/// only; its rep drops within one weight are the small steps of the ladder.
ProgressionTarget gapDeloadTarget(ProgressionInputs s, int steps) {
  final weightFloor = s.weight * (1 - kGapDeloadMaxLoss);
  final repsFloor = (s.reps * (1 - kGapDeloadMaxLoss)).ceil();
  var cur = s;
  for (var i = 0; i < steps; i++) {
    final t = targetAfterFailure(cur);
    if (t.weight == cur.weight && t.reps == cur.reps) break;
    // A tiny epsilon: 0.6 * 12.5 is 7.499999... in binary.
    if (t.weight < weightFloor - 1e-9) break;
    if (s.mode == ProgressionMode.reps && t.reps < repsFloor) break;
    cur = _Step(s, t);
  }
  return ProgressionTarget(cur.weight, cur.reps);
}

/// One finished session of one exercise: when it ended and its target.
class SessionMark {
  /// Creates a [SessionMark].
  const SessionMark({
    required this.endedAt,
    required this.weight,
    required this.reps,
  });

  /// When the session ended (local time).
  final DateTime endedAt;

  /// The target weight the session was done at, in kg.
  final double weight;

  /// The target reps the session was done at.
  final int reps;
}

/// Steps the history still owes: the replay (part c) of the backfill.
///
/// Replays [marks] (oldest first) with the new rule. Each gap of a week or
/// more between two sessions should have cut the next one's target; when the
/// next session ran at the SAME target, that cut never happened and its
/// steps are owed. Any target change afterwards (a fail-streak deload, a
/// success step, a hand edit) re-anchors the replay on what was really
/// lifted, so the debt clears. That is kuhy's case: failed after a 7-day
/// break at the pre-gap weight, then a second break on top.
int missedGapSteps(List<SessionMark> marks) {
  var owed = 0;
  for (var i = 1; i < marks.length; i++) {
    final prev = marks[i - 1];
    final cur = marks[i];
    if (cur.weight != prev.weight || cur.reps != prev.reps) {
      owed = 0;
      continue;
    }
    owed += gapDeloadSteps(gapCalendarDays(prev.endedAt, cur.endedAt));
  }
  return owed;
}

/// [ProgressionInputs] of [base] with [t]'s weight and reps: one step down.
class _Step implements ProgressionInputs {
  _Step(this._base, this._t);

  final ProgressionInputs _base;
  final ProgressionTarget _t;

  @override
  double get weight => _t.weight;

  @override
  int get reps => _t.reps;

  @override
  double get maxWeight => _base.maxWeight;

  @override
  ProgressionMode get mode => _base.mode;

  @override
  int get repsHigh => _base.repsHigh;

  @override
  int get repsLow => _base.repsLow;
}
