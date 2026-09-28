/// Whether a synced workout already covers a given day.
///
/// The home screen opens a fresh workout by itself on launch unless one
/// already counts for today -- and "counts" is wider than this phone's own
/// history: a manual workout, the PC's verified RunnerUp run, or a session
/// logged on another device all mean there is nothing left to push for.
library;

/// The `YYYY-MM-DD` key a workout record is dated with.
///
/// The PC dates every synced record by its `log.json` day key, which is a
/// local calendar day -- the same calendar [DateTime.now] reads on the phone.
String dayKey(DateTime day) =>
    '${day.year.toString().padLeft(4, '0')}-'
    '${day.month.toString().padLeft(2, '0')}-'
    '${day.day.toString().padLeft(2, '0')}';

/// Whether any of [payloads] (merged cross-device workout records) is dated
/// [day].
///
/// A prefix match, so both a bare `2026-09-28` and a full ISO timestamp from
/// a StrongLifts session read as the same day.
bool anyWorkoutOn(Iterable<Map<String, dynamic>> payloads, DateTime day) {
  final key = dayKey(day);
  return payloads.any((p) => '${p['date']}'.startsWith(key));
}
