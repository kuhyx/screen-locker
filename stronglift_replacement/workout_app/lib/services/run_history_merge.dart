/// Merges the phone's own runs into the history list without doubling them.
///
/// The PC pushes a `runnerup_verified` calendar entry for every day it
/// credited a RunnerUp run or walk. Once the app records (or imports) the same
/// run itself, that entry says nothing the local run does not, and the local
/// one has the map. This hides the duplicate.
///
/// The key is **day + sport**, not a start time, because that is all the PC
/// entry carries: its record id is `runnerup_verified:<YYYY-MM-DD>` (one slot
/// per day, runs and walks merged), and the payload holds `date`,
/// `distance_km`, `duration_minutes`, an optional `completed_at` (the *end*,
/// often absent) and `activity: walking` for a day of walks. There is no
/// start time to match within a window. Sport keeps a stock-RunnerUp run
/// visible next to an app-recorded walk on the same day.
///
/// When nothing matches, both stay visible: a duplicate is a nuisance, a
/// hidden credited run is a lie.
library;

import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/done_today.dart';

/// The `kind` the PC gives its run/walk entries.
const kRunnerUpVerifiedKind = 'runnerup_verified';

String _key(RunSport sport, String day) => '${sport.tcxName}|$day';

/// The `YYYY-MM-DD` part of a PC entry's `date`.
String _entryDay(Map<String, dynamic> payload) {
  final date = '${payload['date']}';
  return date.length > 10 ? date.substring(0, 10) : date;
}

/// The sport a PC entry stands for: a day of walks says so, anything else is
/// a run.
RunSport _entrySport(Map<String, dynamic> payload) =>
    payload['activity'] == 'walking' ? RunSport.walking : RunSport.running;

/// [synced] without the `runnerup_verified` entries that [runs] already
/// cover (same local day and same sport).
///
/// Days are the device's local calendar days, the calendar the PC dates its
/// records by (`dayKey`). Other kinds pass through untouched.
List<Map<String, dynamic>> withoutLocalRuns(
  List<Map<String, dynamic>> synced,
  Iterable<RunRecord> runs,
) {
  final covered = {
    for (final r in runs)
      _key(r.track.sport, dayKey(r.track.startedAt.toLocal())),
  };
  return [
    for (final p in synced)
      if (p['kind'] != kRunnerUpVerifiedKind ||
          !covered.contains(_key(_entrySport(p), _entryDay(p))))
        p,
  ];
}
