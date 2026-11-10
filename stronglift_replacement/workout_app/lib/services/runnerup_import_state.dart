/// What the RunnerUp import remembers and reports: prefs keys, the live
/// status the badge shows, and the per-pass tally.
library;

import 'package:flutter/foundation.dart';

/// Where RunnerUp itself leaves exports on the phone.
const String kRunnerUpLocalDir = '/sdcard/Documents/RunnerUp';

/// `shared_preferences` key: every remote export is in the database.
const String kImportDoneKey = 'runnerup_import_done';

/// `shared_preferences` key: the marker JSON, kept until the PC has it.
const String kImportMarkerKey = 'runnerup_import_marker';

/// What the badge shows.
enum RunnerUpImportStatus {
  /// Not started, or not applicable here (sandbox, desktop).
  idle,

  /// Importing right now.
  running,

  /// Imported and the PC has been told.
  done,

  /// Something failed; the next app start retries.
  failed,
}

/// The live status; the badge listens to it.
final ValueNotifier<RunnerUpImportStatus> runnerUpImportStatus = ValueNotifier(
  RunnerUpImportStatus.idle,
);

/// What one [RunnerUpImporter.runIfNeeded] pass did.
typedef RunnerUpImportReport = ({
  int imported,
  int duplicates,
  int skipped,
  List<String> failures,
});

/// The report of a pass that did nothing.
const RunnerUpImportReport kNothingImported = (
  imported: 0,
  duplicates: 0,
  skipped: 0,
  failures: [],
);

/// Counts one import pass and logs each failure as it happens.
class ImportTally {
  /// Runs stored this pass.
  int imported = 0;

  /// Exports already stored (same hash or id).
  int duplicates = 0;

  /// Files that are no usable run, skipped for good.
  int skipped = 0;

  /// Why the pass is incomplete; empty means it can finish.
  final List<String> failures = [];

  /// Records [reason] and logs it as a warning.
  void fail(String reason) {
    failures.add(reason);
    debugPrint('WorkoutApp: RunnerUp import WARNING: $reason');
  }

  /// The tally as a report.
  RunnerUpImportReport get report => (
    imported: imported,
    duplicates: duplicates,
    skipped: skipped,
    failures: failures,
  );
}
