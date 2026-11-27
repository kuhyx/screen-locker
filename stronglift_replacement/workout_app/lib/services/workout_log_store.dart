/// This device's copy of the shared workout log: outbox and cache in one.
///
/// Offline-first (crdt_sync_dart README, "Offline-first contract"): a finished
/// workout's record lands here before any network call, so a failed or
/// unconfigured push keeps it and the next tick sends it. Every tick, and
/// every live history read, merges what it pulled back in, so the PC's
/// records stay readable offline and after a restart.
library;

import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/services/sync_device_id.dart';

/// File holding the log, beside `sync_state.json` (the revisions it backs).
const kWorkoutLogFileName = 'workout_log.json';

/// Replaces the app support directory as the log's home when non-null.
///
/// `test/flutter_test_config.dart` points it at a fresh temp directory for
/// every test; nothing in the app sets it.
@visibleForTesting
String? workoutLogDirOverride;

Future<LogStore>? _shared;
String? _sharedDir;

/// The process-wide store, loaded once.
///
/// One instance on purpose: two stores over one file would each hold a
/// stale copy and the later write would drop the other's records.
Future<LogStore> openWorkoutLogStore() async {
  final dir = workoutLogDirOverride ?? await _supportDir();
  if (_shared == null || _sharedDir != dir) {
    _sharedDir = dir;
    _shared = openWorkoutLogStoreIn(dir);
  }
  return await _shared!;
}

/// Opens and loads a store over [dirPath]/[kWorkoutLogFileName].
Future<LogStore> openWorkoutLogStoreIn(String dirPath) async {
  final store = LogStore(
    persistence: FileLogPersistence(File(p.join(dirPath, kWorkoutLogFileName))),
    nodeId: currentSyncDeviceId,
  );
  await store.load();
  return store;
}

/// The app support directory, where the app keeps its sync state.
Future<String> _supportDir() async =>
    (await getApplicationSupportDirectory()).path;
