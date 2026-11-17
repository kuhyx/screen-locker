/// The run screen's side of a recording: location access, the foreground
/// service, the link to the host that holds the run, and the view of it.
///
/// The recording itself (GPS stream, numbers, checkpoint, cues, the save)
/// lives in the host. This controller can be disposed, replaced or killed at
/// any moment without touching the run: [dispose] only hangs up.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/idle_location.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_link.dart';
import 'package:workout_app/services/run_notification.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_view.dart';
import 'package:workout_app/services/run_wire.dart';

/// How long a command may wait for the host's answer before the screen stops
/// waiting (and says so in the log).
const kRunHostTimeout = Duration(seconds: 20);

/// Owns the [RunView] and everything the UI must do around a recording.
///
/// Order matters at the start: location access first, then the foreground
/// service (Android 14 refuses a `location` service without the permission),
/// then the host's first fix.
class RunController extends ChangeNotifier {
  /// Creates a controller over [link]; [idleSourceFor] feeds the idle map.
  RunController({
    required PositionSource Function() idleSourceFor,
    required this._service,
    required this._link,
    required this._soundOn,
    this.hostTimeout = kRunHostTimeout,
    this.retryEvery = const Duration(milliseconds: 750),
  }) {
    _idle = IdleLocation(idleSourceFor(), onAccess: _onAccess);
    view.addListener(notifyListeners);
    view.onNeedSync = _hello;
    _sub = _link.messages.listen(_onMessage);
  }

  /// What the screen shows.
  final view = RunView();

  /// How long to wait for the host.
  final Duration hostTimeout;

  /// How often [attach] asks again while the host is silent.
  final Duration retryEvery;

  late final IdleLocation _idle;
  final ForegroundRunClient _service;
  final RunLink _link;
  final Future<bool> Function() _soundOn;
  late final StreamSubscription<Map<Object?, Object?>> _sub;

  RunServiceState _serviceState = RunServiceState.none;
  bool _disposed = false;
  bool _attachGaveUp = false;

  /// The host never answered the screen's questions: nothing is there.
  bool get attachGaveUp => _attachGaveUp;

  /// Whether the foreground service is up (and with a notification).
  RunServiceState get serviceState => _serviceState;

  /// What saving the finished run did, once it ran.
  RunSaveResult? get saved => view.saved == null
      ? null
      : RunSaveResult(
          stored: view.saved!.stored,
          reason: view.saved!.reason,
        );

  /// True while the finished run is being written.
  bool get saving =>
      view.saving || (view.phase == RunPhase.finished && !view.done);

  /// True from start to finish: the screen must not be left meanwhile.
  bool get active => view.phase.isActive;

  /// Where the user is before the run starts (display only, never recorded).
  ValueListenable<LatLng?> get position => _idle.position;

  /// True while location is refused and the run has not started: the screen
  /// shows only the problem icon, no map and no start.
  bool get blocked => view.phase == RunPhase.idle && view.issue.isAccess;

  /// Whether access has been found granted, so a start cannot race a prompt.
  bool get canStart => _idle.access?.isGranted ?? false;

  /// Asks for location (this may show the prompt) and starts watching the
  /// position for the idle map. Also the retry after a refusal.
  Future<void> watchIdle() => _idle.open();

  /// Re-reads the access silently (the app came back to the foreground).
  Future<void> recheckAccess() =>
      view.phase == RunPhase.idle ? _idle.recheck() : Future.value();

  /// Asks the host where the run stands (and keeps asking until it answers:
  /// a restarted service needs a moment to come up).
  Future<void> attach() async {
    for (var i = 0; i < 8 && !view.synced && !_disposed; i++) {
      _hello();
      await Future<void>.delayed(i == 0 ? Duration.zero : retryEvery);
    }
    if (!view.synced && !_disposed) {
      _attachGaveUp = true;
      _serviceState = RunServiceState.none;
    } else if (view.phase.isActive && !_serviceState.isUp) {
      _serviceState = RunServiceState.running;
    }
    notifyListeners();
  }

  /// Asks for access, starts the service, begins recording. A run that is
  /// already going is never restarted.
  Future<void> start({int? paceTarget}) async {
    if (view.phase.isActive) return;
    await _idle.stop();
    await _startService();
    await attach();
    _link.send({
      'cmd': RunCmd.start,
      'paceTarget': paceTarget,
      'sound': await _soundOn(),
    });
    await _until(() => view.phase.isActive || view.issue != RunIssue.none);
    // A refused start leaves the screen blocked; let a resume recheck it.
    if (!view.phase.isActive && view.issue.isAccess) _idle.reopen();
  }

  /// Pauses crediting.
  void pause() => _link.send({'cmd': RunCmd.pause});

  /// Resumes crediting.
  void resume() => _link.send({'cmd': RunCmd.resume});

  /// Changes the pace target of a running recording.
  void setPaceTarget(int? seconds) =>
      _link.send({'cmd': RunCmd.paceTarget, 'paceTarget': seconds});

  /// Tells the host the finish modal the notification asked for is showing.
  void ackPrompt() => _link.send({'cmd': RunCmd.ackPrompt});

  /// Ends the run and waits until the host has saved it. Only the screen's
  /// confirm modal calls this.
  Future<void> finish() async {
    _link.send({'cmd': RunCmd.finish});
    await _until(
      () => view.phase == RunPhase.finished && view.done,
    );
    if (view.phase == RunPhase.finished) {
      _serviceState = RunServiceState.none;
      notifyListeners();
    }
  }

  void _hello() => _link.send({'cmd': RunCmd.hello});

  void _onMessage(Map<Object?, Object?> message) {
    if (!isRunMessage(message)) return;
    view.apply(message);
    if (view.phase.isActive && !_serviceState.isUp) {
      _serviceState = RunServiceState.running;
    }
  }

  Future<void> _until(bool Function() done) async {
    if (done()) return;
    final completer = Completer<void>();
    void check() {
      if (done() && !completer.isCompleted) completer.complete();
    }

    view.addListener(check);
    try {
      await completer.future.timeout(hostTimeout);
    } on TimeoutException {
      log(
        'RunController: the run host did not answer within '
        '${hostTimeout.inSeconds}s (phase ${view.phase.name}, issue '
        '${view.issue.name}). The run itself is not touched; reopen the '
        'screen to ask again.',
        level: 1000,
      );
    } finally {
      view.removeListener(check);
    }
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
    final started = await _service.start(
      withLocation: true,
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

  void _onAccess(LocationAccess access) {
    view.noteAccess(access);
    // canStart follows the access, which the view does not report.
    notifyListeners();
  }

  /// Hangs up. The run, if any, goes on in the host.
  @override
  void dispose() {
    _disposed = true;
    unawaited(_sub.cancel());
    unawaited(_idle.dispose());
    unawaited(_link.close());
    view
      ..removeListener(notifyListeners)
      ..dispose();
    super.dispose();
  }
}
