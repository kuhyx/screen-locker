/// The UI's line to the run host, and the in-process version of it.
library;

import 'dart:async';

import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_host.dart';

/// A conversation with the host. Closing it only hangs up: it never touches
/// the run.
abstract interface class RunLink {
  /// The host's snapshots (see `run_wire.dart`).
  Stream<Map<Object?, Object?>> get messages;

  /// Sends a command (`cmd` key); a host that is not up never answers.
  void send(Map<String, Object?> command);

  /// Hangs up.
  Future<void> close();
}

/// The host's side of a [LoopbackRunLink]: messages go to the link's stream,
/// the notification and the service go through the [ForegroundRunClient].
class LoopbackRunPort implements RunHostPort {
  /// Creates a port over [_client].
  LoopbackRunPort(this._client);

  final ForegroundRunClient _client;
  final _out = StreamController<Map<Object?, Object?>>.broadcast(sync: true);

  /// What the host sends.
  Stream<Map<Object?, Object?>> get messages => _out.stream;

  @override
  void send(Map<String, Object?> message) => _out.add(message);

  @override
  Future<void> notify({required String title, required String text}) =>
      _client.update(title: title, text: text);

  @override
  Future<void> stopService() => _client.stop();

  @override
  void launchApp() {}
}

/// A [RunLink] to a host in this very isolate: Linux, the tests, and any
/// platform with no foreground service.
class LoopbackRunLink implements RunLink {
  /// Creates a link to [host]; [port] is the one the host was built with.
  LoopbackRunLink(this.host, this._port);

  /// Builds the host and its link in one go.
  factory LoopbackRunLink.build({
    required ForegroundRunClient client,
    required RunEngineFactory engineFactory,
    required FeedbackCues cues,
    required RunSaveFn save,
    RunCheckpointStore? store,
  }) {
    final port = LoopbackRunPort(client);
    final host = RunHost(
      engineFactory: engineFactory,
      port: port,
      store: store ?? MemoryRunCheckpointStore(),
      cues: cues,
      save: save,
    );
    return LoopbackRunLink(host, port);
  }

  /// The in-process host.
  final RunHost host;
  final LoopbackRunPort _port;

  @override
  Stream<Map<Object?, Object?>> get messages => _port.messages;

  @override
  void send(Map<String, Object?> command) => unawaited(host.handle(command));

  @override
  Future<void> close() async {}
}

/// A checkpoint kept in memory: enough where nothing can kill the process
/// separately from the UI.
class MemoryRunCheckpointStore implements RunCheckpointStore {
  RunCheckpoint? _held;

  @override
  Future<void> save(RunCheckpoint c) async => _held = c;

  @override
  Future<RunCheckpoint?> load() async => _held;

  @override
  Future<void> clear() async => _held = null;
}
