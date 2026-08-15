// Rolling manual-workout budget accounting.
//
// See manual_workout_validation.dart for why these are `part` files.
part of 'manual_workout.dart';

/// Counts DAYS with a manual workout in the rolling 7-/30-day windows.
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
ManualBudget countManualBudget(
  Iterable<Map<String, dynamic>> payloads,
  DateTime now,
) {
  final today = DateTime(now.year, now.month, now.day);
  var week = 0;
  var month = 0;
  for (final payload in payloads) {
    final dateStr = payload['date'];
    if (dateStr is! String) continue;
    final date = DateTime.tryParse(dateStr);
    if (date == null) continue;
    final days = today
        .difference(DateTime(date.year, date.month, date.day))
        .inDays;
    if (days < 0) continue;
    if (days < 7) week++;
    if (days < 30) month++;
  }
  return ManualBudget(week: week, month: month);
}
