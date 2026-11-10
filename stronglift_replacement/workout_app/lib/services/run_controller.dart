/// Wires one recording to the phone: permission, foreground service, cues,
/// notification and the save at the end.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_notification.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_saver.dart';

/// Owns a [RunRecorder] and everything that must happen around it.
///
/// Order matters at the start: location access first (the recorder asks), then
/// the foreground service (Android 14 refuses a `location` service without
/// the permission), then the first fix.
class RunController extends ChangeNotifier {
  /// Creates a controller; it builds its own [recorder] over [sourceFor].
  RunController({
    required PositionSource Function(RunSport sport) sourceFor,
    required this._service,
    required this._cues,
    required this._save,
  }) {
    recorder = RunRecorder(sourceFor: sourceFor, onKilometre: _onKilometre)
      ..addListener(_onRecorderChanged);
  }

  /// The state machine; the live map reads its points.
  late final RunRecorder recorder;

  final ForegroundRunClient _service;
  final FeedbackCues _cues;
  final Future<RunSaveResult> Function(RunTrack track) _save;

  RunServiceState _serviceState = RunServiceState.none;
  RunSaveResult? _saved;
  bool _saving = false;
  String _lastCopy = '';

  /// Whether the foreground service is up (and with a notification).
  RunServiceState get serviceState => _serviceState;

  /// What saving the finished run did, once it ran.
  RunSaveResult? get saved => _saved;

  /// True while the finished run is being written.
  bool get saving => _saving;

  /// True from start to finish: the screen must not be left meanwhile.
  bool get active =>
      recorder.phase == RunPhase.recording || recorder.phase == RunPhase.paused;

  /// Asks for access, starts the service, begins recording.
  Future<void> start() async {
    await _cues.load();
    await recorder.start(afterAccess: _startService);
  }

  /// Pauses crediting.
  void pause() => recorder.pause();

  /// Resumes crediting.
  void resume() => recorder.resume();

  /// Ends the run, stops the service and saves the track.
  Future<void> finish() async {
    final track = await recorder.finish();
    await _stopService();
    if (track == null) return;
    unawaited(_cues.workoutFinished());
    _saving = true;
    notifyListeners();
    try {
      _saved = await _save(track);
    } on Exception catch (error, stack) {
      log(
        'RunController: saving ${track.id} failed ($error) -- the run is '
        'lost unless it is recorded again.',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
      _saved = RunSaveResult(stored: false, reason: 'save failed: $error');
    }
    _saving = false;
    notifyListeners();
  }

  Future<void> _startService() async {
    if (!_service.isSupported) {
      _serviceState = RunServiceState.unsupported;
      return;
    }
    var shown = await _service.hasNotificationPermission();
    if (!shown) shown = await _service.requestNotificationPermission();
    if (!shown) {
      log(
        'RunController: notification permission denied. The run still '
        'records, but the status-bar distance and time cannot be shown.',
        level: 1000,
      );
    }
    final copy = runNotificationCopy(metres: 0, movingSeconds: 0);
    _lastCopy = '${copy.title}|${copy.body}';
    final started = await _service.start(
      withLocation: !Sandbox.enabled,
      title: copy.title,
      text: copy.body,
    );
    if (!started) {
      _serviceState = RunServiceState.failed;
      log(
        'RunController: the foreground service refused to start. GPS fixes '
        'may stop when the screen turns off -- keep the app open.',
        level: 1000,
      );
      return;
    }
    _serviceState = shown
        ? RunServiceState.running
        : RunServiceState.runningHidden;
  }

  Future<void> _stopService() async {
    if (_serviceState != RunServiceState.running &&
        _serviceState != RunServiceState.runningHidden) {
      return;
    }
    await _service.stop();
    _serviceState = RunServiceState.none;
    notifyListeners();
  }

  void _onKilometre(int km) => unawaited(_cues.kilometreReached(km));

  void _onRecorderChanged() {
    if (_serviceState == RunServiceState.running) {
      final copy = runNotificationCopy(
        metres: recorder.distanceM,
        movingSeconds: recorder.seconds,
      );
      // Only when the words changed: an update per fix would redraw twice a
      // second for nothing.
      if ('${copy.title}|${copy.body}' != _lastCopy) {
        _lastCopy = '${copy.title}|${copy.body}';
        unawaited(_service.update(title: copy.title, text: copy.body));
      }
    }
    notifyListeners();
  }

  @override
  void dispose() {
    recorder
      ..removeListener(_onRecorderChanged)
      ..dispose();
    if (active) unawaited(_service.stop());
    super.dispose();
  }
}
