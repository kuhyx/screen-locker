// coverage:ignore-file
// A path_provider lookup only the phone can answer; the logic around it is
// tested against in-memory stores.
/// Where the active run's checkpoint lives on disk, for every isolate.
library;

import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';

/// Opens the one checkpoint file of the app (shared by the UI isolate, the
/// service isolate and the boot path).
Future<RunCheckpointStore> openRunCheckpointStore() async {
  final dir = await getApplicationSupportDirectory();
  return FileRunCheckpointStore(File(p.join(dir.path, 'run_checkpoint.json')));
}

/// Whether a run is owed: its checkpoint is on disk. While true the shared
/// foreground service belongs to the run, and nothing else may stop or
/// replace it.
Future<bool> runIsOwed() async =>
    await (await openRunCheckpointStore()).load() != null;
