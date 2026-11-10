/// Wires one recording to the phone: permission, foreground service, cues,
/// notification and the save at the end.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/idle_location.dart';
import 'package:workout_app/services/pace_band.dart';
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
  ///
  /// [idleSourceFor] feeds the idle map before the run (display only); it
  /// defaults to [sourceFor].
  RunController({
    required PositionSource Function() sourceFor,
    required this._service,
    required this._cues,
    required this._save,
    PositionSource Function()? idleSourceFor,
  }) {
    recorder = RunRecorder(
      sourceFor: sourceFor,
      onKilometre: _onKilometre,
      onPaceCue: _onPaceCue,
    )..addListener(_onRecorderChanged);
    _idle = IdleLocation((idleSourceFor ?? sourceFor)(), onAccess: _onAccess);
  }

  /// The state machine; the live map reads its points.
  late final RunRecorder recorder;

  late final IdleLocation _idle;
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
  bool get active => recorder.phase.isActive;

  /// Where the user is before the run starts (display only, never recorded).
  ValueListenable<LatLng?> get position => _idle.position;

  /// True while location is refused and the run has not started: the screen
  /// shows only the problem icon, no map and no start.
  bool get blocked =>
      recorder.phase == RunPhase.idle && recorder.issue.isAccess;

  /// Whether access has been found granted, so a start cannot race a prompt.
  bool get canStart => _idle.access?.isGranted ?? false;

  /// Asks for location (this may show the prompt) and starts watching the
  /// position for the idle map. Also the retry after a refusal.
  Future<void> watchIdle() => _idle.open();

  /// Re-reads the access silently (the app came back to the foreground).
  Future<void> recheckAccess() =>
      recorder.phase == RunPhase.idle ? _idle.recheck() : Future.value();

  /// Asks for access, starts the service, begins recording.
  Future<void> start() async {
    await _idle.stop();
    await _cues.load();
    final started = await recorder.start(afterAccess: _startService);
    // A refused start leaves the screen blocked; let a resume recheck it.
    if (!started && recorder.issue.isAccess) _idle.reopen();
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
    if (!_serviceState.isUp) return;
    await _service.stop();
    _serviceState = RunServiceState.none;
    notifyListeners();
  }

  void _onKilometre(int km) => unawaited(_cues.kilometreReached(km));

  void _onPaceCue(PaceCue cue) => unawaited(_cues.paceOff(cue));

  void _onAccess(LocationAccess access) {
    recorder.noteAccess(access);
    // canStart follows the access, which the recorder does not report.
    notifyListeners();
  }

  void _onRecorderChanged() {
    if (_serviceState == RunServiceState.running) {
      final copy = runNotificationCopy(
        metres: recorder.distanceM,
        movingSeconds: recorder.seconds,
        currentPace: recorder.coach.target == null ? null : recorder.coach.pace,
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
    unawaited(_idle.dispose());
    recorder
      ..removeListener(_onRecorderChanged)
      ..dispose();
    if (active) unawaited(_service.stop());
    super.dispose();
  }
}
