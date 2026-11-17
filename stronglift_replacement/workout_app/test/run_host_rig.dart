/// A [RunHost] over fakes, with every outward call recorded.
library;

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_host.dart';

import 'fake_run_engine.dart';
import 'fake_run_service.dart';
import 'run_test_fixtures.dart';

/// A port that remembers everything.
class FakePort implements RunHostPort {
  /// Messages sent to the UI.
  final sent = <Map<String, Object?>>[];

  /// Notification redraws as `title|text`.
  final notes = <String>[];

  /// How often the service was stopped.
  int stops = 0;

  /// How often the app was brought forward.
  int launches = 0;

  /// The newest message.
  Map<String, Object?> get last => sent.last;

  @override
  void send(Map<String, Object?> message) => sent.add(message);

  @override
  Future<void> notify({required String title, required String text}) async =>
      notes.add('$title|$text');

  @override
  Future<void> stopService() async => stops++;

  @override
  void launchApp() => launches++;
}

/// A store in memory that can be told to fail.
class FakeStore implements RunCheckpointStore {
  /// The held checkpoint.
  RunCheckpoint? held;

  /// Saves that went through.
  int saves = 0;

  /// Clears.
  int clears = 0;

  /// Makes [save] throw.
  bool failSave = false;

  @override
  Future<void> save(RunCheckpoint c) async {
    if (failSave) throw Exception('disk full');
    saves++;
    held = c;
  }

  @override
  Future<RunCheckpoint?> load() async => held;

  @override
  Future<void> clear() async {
    clears++;
    held = null;
  }
}

/// Everything a host test touches.
class HostRig {
  /// Builds the rig; [save] defaults to "stored".
  HostRig({
    this.saveThrows = false,
    this.saveStores = true,
    RunHostPort? hostPort,
  }) {
    host = RunHost(
      engineFactory: (hooks) {
        lastHooks = hooks;
        final engine = FakeRunEngine(
          startResult: startResult,
          restoreResult: restoreResult,
        )..track = sampleTrack();
        engines.add(engine);
        return engine;
      },
      port: hostPort ?? port,
      store: store,
      cues: cues,
      save: (track) async {
        if (saveThrows) throw Exception('db locked');
        saved.add(track);
        return (stored: saveStores, reason: 'saved');
      },
    );
  }

  /// Whether the save throws.
  final bool saveThrows;

  /// What the save answers.
  final bool saveStores;

  /// What new engines answer to start / restore.
  bool startResult = true;

  /// See [startResult].
  bool restoreResult = true;

  /// The host under test.
  late final RunHost host;

  /// Recorded port.
  final port = FakePort();

  /// Recorded store.
  final store = FakeStore();

  /// Recorded cues.
  final cues = QuietCues();

  /// Tracks the host saved.
  final saved = <RunTrack>[];

  /// Every engine the host built, oldest first.
  final engines = <FakeRunEngine>[];

  /// The hooks of the newest engine.
  late RunEngineHooks lastHooks;

  /// The newest engine.
  FakeRunEngine get engine => engines.last;

  /// Sends a UI command.
  Future<void> cmd(String name, [Map<String, Object?> extra = const {}]) =>
      host.handle({'cmd': name, ...extra});
}
