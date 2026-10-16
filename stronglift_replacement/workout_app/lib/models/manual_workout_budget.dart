// Rolling manual-workout budget accounting.
//
// See manual_workout_validation.dart for why these are `part` files.
part of 'manual_workout.dart';

/// Counts manual workouts against the rolling 7-/30-day caps, as seen from
/// the workout date [date].
///
/// The budget is counted per ENTRY, not per day: each self-report consumes its
/// own slot, so three workouts logged on one day cost three. That matches the
/// PC's `count_in_window` (screen_locker/_manual_workout.py), which is the
/// source of truth — each entry separately earns weekly-count and shutdown
/// credit, so each must separately cost budget.
///
/// This counted DAYS until 2026-08-09 (a `Set` of date strings) while the PC
/// counted entries, so three same-day workouts read as 3/2 on the PC — over
/// its 7-day cap — but 1/2 here, and the phone kept accepting. Callers pass
/// one payload per synced record (`manual:<date>T<HH:MM>`), so same-day
/// workouts at different times arrive as distinct payloads.
///
/// Since 2026-10-16 a workout can be PLANNED up to a week ahead, so the count
/// is no longer "the trailing window ending today". Each figure is the
/// fullest window of that length that contains [date], counting past and
/// future entries alike: adding an entry on [date] is only allowed if every
/// such window stays within its cap, and the fullest one is the binding
/// constraint. With no future entries and [date] = today this is exactly the
/// old trailing count, since every other window holds a subset of it.
ManualBudget countManualBudget(
  Iterable<Map<String, dynamic>> payloads,
  DateTime date,
) {
  final target = _dayNumber(date);
  // Offsets (in days) of every counted entry relative to [date].
  final offsets = <int>[];
  for (final payload in payloads) {
    // Skip evidence-less `{type, kind, date}` stubs. The PC refuses to ingest
    // these ("no workout data to ingest; skipping permanently"), so counting
    // them made the phone's budget stricter than the PC's for a workout that
    // neither device ever accepted. `start_time` is the discriminator: every
    // real self-report has one, and no stub does.
    if (payload['start_time'] is! String) continue;
    final dateStr = payload['date'];
    if (dateStr is! String) continue;
    final entryDate = DateTime.tryParse(dateStr);
    if (entryDate == null) continue;
    offsets.add(_dayNumber(entryDate) - target);
  }
  return ManualBudget(
    week: _fullestWindow(offsets, 7),
    month: _fullestWindow(offsets, 30),
  );
}

/// Days since the epoch for [day]'s calendar date.
///
/// Built in UTC so a DST change between two local midnights (a 23- or 25-hour
/// "day") cannot truncate a one-day difference to zero.
int _dayNumber(DateTime day) =>
    DateTime.utc(day.year, day.month, day.day).millisecondsSinceEpoch ~/
    Duration.millisecondsPerDay;

/// The most entries any [length]-day window containing offset 0 holds.
int _fullestWindow(List<int> offsets, int length) {
  var fullest = 0;
  // A window containing day 0 starts anywhere from `length - 1` days before
  // it up to day 0 itself.
  for (var start = 1 - length; start <= 0; start++) {
    final end = start + length - 1;
    final count = offsets.where((o) => o >= start && o <= end).length;
    if (count > fullest) fullest = count;
  }
  return fullest;
}
