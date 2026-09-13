import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_notification_text.dart';

BreakSnapshot snap({
  int breakEndMs = 0,
  int breakDurationSecs = 0,
  int nextExIdx = 0,
  int nextSetIdx = 2,
  String nextExName = 'Squat',
  int nextSetNumber = 3,
  int nextTotalSets = 5,
  int nextReps = 5,
  double nextWeight = 40,
  int setsRemaining = 3,
  bool finished = false,
}) => BreakSnapshot(
  workoutType: 'A',
  breakEndMs: breakEndMs,
  breakDurationSecs: breakDurationSecs,
  breakLabel: 'Rest',
  breakForExIdx: 0,
  breakForSetIdx: 1,
  nextExIdx: nextExIdx,
  nextSetIdx: nextSetIdx,
  nextExName: nextExName,
  nextSetNumber: nextSetNumber,
  nextTotalSets: nextTotalSets,
  nextReps: nextReps,
  nextWeight: nextWeight,
  lastExIdx: 0,
  lastSetIdx: 1,
  setsRemaining: setsRemaining,
  finished: finished,
);

void main() {
  final now = DateTime(2026, 9, 12, 14);

  test('shows the countdown in the title, which Android shows collapsed', () {
    final copy = BreakNotificationText.render(
      snap(
        breakEndMs: now.add(const Duration(seconds: 107)).millisecondsSinceEpoch,
        breakDurationSecs: 180,
      ),
      now,
    );
    expect(copy.title, 'Workout A · break 1:47');
    expect(copy.body, 'Next: Squat — set 3/5\n5 reps @ 40 kg');
  });

  test('says the break is over once the deadline has passed', () {
    final copy = BreakNotificationText.render(
      snap(
        breakEndMs: now.subtract(const Duration(seconds: 5)).millisecondsSinceEpoch,
        breakDurationSecs: 180,
      ),
      now,
    );
    expect(copy.title, 'Workout A · break over');
  });

  test('says lift when no rest is running', () {
    expect(BreakNotificationText.render(snap(), now).title, 'Workout A · lift');
  });

  test('says so when every set is recorded', () {
    final copy = BreakNotificationText.render(
      snap(nextExIdx: -1, nextSetIdx: -1, setsRemaining: 0),
      now,
    );
    expect(copy.body, 'Every set is done — finish the workout.');
  });

  test('a finished workout asks to be saved', () {
    final copy = BreakNotificationText.render(snap(finished: true), now);
    expect(copy.title, 'Workout complete');
    expect(copy.body, 'Open the app to save it.');
  });

  test('drops a pointless trailing zero from the weight', () {
    expect(BreakNotificationText.formatWeight(40), '40');
    expect(BreakNotificationText.formatWeight(22.5), '22.5');
    expect(BreakNotificationText.formatWeight(7.5), '7.5');
    expect(BreakNotificationText.formatWeight(0), '0');
  });

  test('formats the countdown as m:ss', () {
    expect(BreakNotificationText.formatMmSs(0), '0:00');
    expect(BreakNotificationText.formatMmSs(9), '0:09');
    expect(BreakNotificationText.formatMmSs(60), '1:00');
    expect(BreakNotificationText.formatMmSs(107), '1:47');
    expect(BreakNotificationText.formatMmSs(300), '5:00');
  });

  // The service only redraws when the text changed, so equality is what keeps
  // the notification from flickering once a second.
  test('copy compares by value', () {
    const a = BreakNotificationCopy('t', 'b');
    const b = BreakNotificationCopy('t', 'b');
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(a, isNot(const BreakNotificationCopy('t', 'other')));
    expect(a, isNot(Object()));
    expect(a.toString(), contains('t | b'));
  });
}
