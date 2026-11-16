/// Shared-storage paths keyed by the running package name.
///
/// `/sdcard` is one directory for every install on the phone. A second
/// install of this code under another package name — a `com.kuhy.slotN`
/// test build — would otherwise read and overwrite the daily build's backup
/// and the workout file the PC pulls. So only the daily package keeps the
/// paths the PC knows; any other package gets a sibling named after itself.
/// The sandbox flavor keeps its own fixed paths (see `Sandbox`).
library;

import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/sync_service.dart';

/// The daily build's application id; the only package that owns the
/// `/sdcard` paths the PC reads.
const String kDailyPackage = 'com.kuhy.workout_app';

/// [dailyPath] for the daily build, `<dailyPath>.<packageName>` otherwise.
String sharedPathFor(String packageName, String dailyPath) =>
    packageName == kDailyPackage ? dailyPath : '$dailyPath.$packageName';

/// Points the backup dir and the workout file at [packageName]'s own paths.
/// Must run before the first read or write of either.
void applySharedStoragePaths(String packageName) {
  BackupService.baseDir = sharedPathFor(packageName, kBackupDir);
  SyncService.filePath = sharedPathFor(packageName, kSyncFilePath);
}
