/// The one place a recording lives: owns the engine, keeps its checkpoint,
/// gives the cues and writes the finished run.
///
/// In production this runs in the foreground-service isolate, so a swiped-away
/// app, a killed UI isolate or a dead process cannot end a run: only
/// [RunCmd.finish] (after the screen's confirm modal) or the 5 h limit does.
/// On Linux and in tests the same class runs in the UI isolate behind a
/// loopback link.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';
import 'package:workout_app/services/run_engine.dart';
import 'package:workout_app/services/run_host_port.dart';
import 'package:workout_app/services/run_notification.dart';
import 'package:workout_app/services/run_wire.dart';

export 'package:workout_app/services/run_host_port.dart';

/// Hosts one recording at a time.
class RunHost {
  /// Creates a host; nothing happens until a command or [restoreFromStore].
  RunHost({
    required this.engineFactory,
    required this.port,
    required this.store,
    required this.cues,
    required this.save,
  });

  /// Builds the recording.
  final RunEngineFactory engineFactory;

  /// Where messages and the notification go.
  final RunHostPort port;

  /// Where the active run's checkpoint lives.
  final RunCheckpointStore store;

  /// The sounds and buzzes.
  final FeedbackCues cues;

  /// Writes a finished track to the database.
  final RunSaveFn save;

  RunEngine? _engine;
  int _sent = 0;
  String? _suggestion;
  bool _prompt = false;
  bool _saving = false;
  bool _finishing = false;
  bool _done = false;
  ({bool stored, String reason})? _saved;
  String _lastCopy = '';

  /// The live engine, if any (tests read it).
  RunEngine? get engine => _engine;

  /// Resumes the run the checkpoint describes. False when there is none (the
  /// caller then has nothing to host).
  Future<bool> restoreFromStore() async {
    final checkpoint = await store.load();
    if (checkpoint == null) return false;
    final engine = _fresh();
    if (!await engine.restore(checkpoint)) {
      log(
        'RunHost: the checkpoint could not be resumed (${engine.issue.name}); '
        'it is kept, and the run screen shows the problem.',
        level: 1000,
      );
    }
    _emit(full: true);
    return true;
  }

  /// Applies one UI command.
  Future<void> handle(Map<Object?, Object?> message) async {
    switch (message['cmd']) {
      case RunCmd.hello:
        _engine ?? _fresh();
        _emit(full: true);
      case RunCmd.start:
        await _start(message);
      case RunCmd.pause:
        _engine?.pause();
      case RunCmd.resume:
        _engine?.resume();
      case RunCmd.paceTarget:
        _engine?.setPaceTarget(message['paceTarget'] as int?);
      case RunCmd.ackPrompt:
        _prompt = false;
        _emit();
      case RunCmd.finish:
        await _finish(auto: false);
      default:
        log('RunHost: unknown command ${message['cmd']} ignored.', level: 900);
    }
  }

  /// The ongoing notification was tapped: with advice standing, the UI opens
  /// on the finish modal (it still needs the check tap).
  void notificationPressed() {
    if (_suggestion != null) {
      _prompt = true;
      _emit();
    }
    port.launchApp();
  }

  RunEngine _fresh() {
    _engine
      ?..removeListener(_onChanged)
      ..dispose();
    _sent = 0;
    _suggestion = null;
    _prompt = false;
    _saved = null;
    _saving = false;
    _done = false;
    return _engine = engineFactory(
      RunEngineHooks(
        onKilometre: (km) => unawaited(cues.kilometreReached(km)),
        onPaceCue: (cue) => unawaited(cues.paceOff(cue)),
        onSuggest: _suggest,
        onAutoEnd: () => unawaited(_finish(auto: true)),
      ),
    )..addListener(_onChanged);
  }

  Future<void> _start(Map<Object?, Object?> message) async {
    final current = _engine;
    if (current != null && current.phase.isActive) {
      // A second "start" can never restart a live run: it only re-syncs.
      return _emit(full: true);
    }
    final engine = _fresh();
    cues.soundOn = message['sound'] as bool? ?? true;
    engine.setPaceTarget(message['paceTarget'] as int?);
    await engine.start();
    _emit(full: true);
  }

  void _suggest(String why) {
    if (_finishing) return;
    _suggestion = why;
    unawaited(cues.finishSuggested());
    _onChanged();
  }

  void _onChanged() {
    final engine = _engine;
    if (engine == null) return;
    if (engine.phase.isActive) {
      saveCheckpointLoudly(store, engine.checkpoint());
      _redrawNotification(engine);
    }
    _emit();
  }

  void _redrawNotification(RunEngine engine) {
    final copy = runNotificationCopy(
      metres: engine.distanceM,
      movingSeconds: engine.seconds,
      currentPace: engine.paceTarget == null ? null : engine.pace,
    );
    final why = _suggestion;
    final title = why == null
        ? copy.title
        : '${suggestionGlyph(why)} ${copy.title}';
    // Only when the words changed: an update per fix redraws twice a second
    // for nothing.
    if ('$title|${copy.body}' == _lastCopy) return;
    _lastCopy = '$title|${copy.body}';
    unawaited(port.notify(title: title, text: copy.body));
  }

  void _emit({bool full = false}) {
    final engine = _engine;
    if (engine == null) return;
    final from = full ? 0 : _sent.clamp(0, engine.points.length);
    port.send(
      encodeSnapshot(
        engine,
        from: from,
        suggestion: _suggestion,
        prompt: _prompt,
        saving: _saving,
        done: _done,
        saved: _saved,
      ),
    );
    _sent = engine.points.length;
  }

  Future<void> _finish({required bool auto}) async {
    final engine = _engine;
    if (engine == null || !engine.phase.isActive || _finishing) return;
    _finishing = true;
    try {
      final track = await engine.finish();
      _suggestion = null;
      _prompt = false;
      unawaited(auto ? cues.autoEnded() : cues.workoutFinished());
      final kept = track != null && !await _saveTrack(track);
      // A save that said "no" (say, a duplicate) still ends the run; only one
      // that threw keeps the checkpoint, so the run is not lost.
      if (!kept) await store.clear();
      _done = true;
      _emit();
      await port.stopService();
    } finally {
      _finishing = false;
    }
  }

  /// Whether the save ran without throwing.
  Future<bool> _saveTrack(RunTrack track) async {
    _saving = true;
    _emit();
    try {
      _saved = await save(track);
      return true;
    } on Exception catch (error, stack) {
      log(
        'RunHost: saving ${track.id} failed ($error) -- the checkpoint is '
        'kept, so the run comes back on the next launch.',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
      _saved = (stored: false, reason: 'save failed: $error');
      return false;
    } finally {
      _saving = false;
    }
  }

  /// Releases the engine (never ends a run).
  void dispose() {
    _engine
      ?..removeListener(_onChanged)
      ..dispose();
    _engine = null;
  }
}
