/// Where the sync revision cache lives on this device.
///
/// Android only — this app has no web target — so unlike the other consumers
/// it needs no conditional export.
library;

import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// File holding the revision cache, beside the workout log it describes.
const kSyncStateFileName = 'sync_state.json';

/// Opens the revision cache in the app's support directory.
// coverage:ignore-start
// Resolves the real per-platform directory, so it cannot run under test;
// [openSyncStateStoreIn] holds the logic and is covered.
Future<SyncStateStore> openSyncStateStore() async {
  final dir = await getApplicationSupportDirectory();
  return openSyncStateStoreIn(dir.path);
}
// coverage:ignore-end

/// Opens the revision cache rooted at [dirPath].
///
/// Must be cleared with the log it describes: skipping an unchanged peer is
/// only sound because that peer's records are already merged locally, so
/// state that outlived its log would skip peers whose data had been lost.
SyncStateStore openSyncStateStoreIn(String dirPath) => PersistedSyncStateStore(
  FileLogPersistence(File(p.join(dirPath, kSyncStateFileName))),
);
