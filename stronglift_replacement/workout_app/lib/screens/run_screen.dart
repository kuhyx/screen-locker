/// The live run screen: map, big numbers, pace target, start/pause/finish.
///
/// One screen, no scrolling (R7), and no words (textgate): icons, colours and
/// digits only. Icons that report a problem are tappable where the fix is in
/// system settings. With location refused there is no map and no start, only
/// the red problem icon; coming back from settings with a grant recovers it.
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/foreground_run_client_flutter.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/pace_target_store.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map_slot.dart';
import 'package:workout_app/widgets/run_pace_picker.dart';
import 'package:workout_app/widgets/run_upload_badge.dart';

part 'run_screen_numbers.dart';
part 'run_screen_parts.dart';

/// The controller the app uses: real GPS (or the sandbox replay), the real
/// foreground service, the real database and the app-wide upload queue.
RunController buildRunController() => RunController(
  sourceFor: positionSourceFor,
  idleSourceFor: idlePositionSourceFor,
  service: FlutterForegroundRunClient(),
  cues: FeedbackCues(AudioPlayer()),
  save: (track) => saveRecordedRun(
    track,
    storage: StorageService.instance,
    enqueue: RunUploader.instance.uploadPending,
  ),
);

/// Builds the live map from the run's accepted points and the user's current
/// position (shown until the run has points).
typedef RunMapBuilder =
    Widget Function(
      BuildContext context,
      ValueListenable<List<RunPoint>> points,
      ValueListenable<LatLng?> position,
    );

/// Records one GPS activity (always a run).
class RunScreen extends StatefulWidget {
  /// Creates the screen; every argument is a test or map seam.
  const RunScreen({
    super.key,
    this.controllerFactory = buildRunController,
    this.uploader,
    this.paceStore,
    this.mapBuilder,
    this.openSettings = openAppSettings,
  });

  /// Builds the controller for a recording (called again for "new run").
  final RunController Function() controllerFactory;

  /// The upload queue shown in the badge; defaults to the app-wide one.
  final RunUploader? uploader;

  /// Where the last pace target is kept; defaults to shared_preferences.
  final PaceTargetStore? paceStore;

  /// Builds the live map; defaults to [RunMapSlot].
  final RunMapBuilder? mapBuilder;

  /// Opens the system settings page for this app.
  final Future<bool> Function() openSettings;

  @override
  State<RunScreen> createState() => _RunScreenState();
}

class _RunScreenState extends State<RunScreen> with WidgetsBindingObserver {
  late RunController _controller = widget.controllerFactory();
  late final RunUploader _uploader = widget.uploader ?? RunUploader.instance;
  late final PaceTargetStore _paceStore =
      widget.paceStore ?? PrefsPaceTargetStore();
  bool _starting = false;
  bool _paceOn = false;
  int _paceTarget = kDefaultPaceTarget;

  @override
  void initState() {
    super.initState();
    SandboxLog.event('open run');
    WidgetsBinding.instance.addObserver(this);
    unawaited(_controller.watchIdle());
    unawaited(_loadPaceTarget());
    // So the badge shows the real queue, not the pre-first-pass default.
    unawaited(_uploader.uploadPending());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // A silent re-check: the permission prompt itself backgrounds the app, so
    // asking again here would loop.
    if (state == AppLifecycleState.resumed) {
      unawaited(_controller.recheckAccess());
    }
  }

  Future<void> _loadPaceTarget() async {
    final stored = await _paceStore.load();
    if (mounted) setState(() => _paceTarget = stored);
  }

  void _setPaceTarget(int seconds) {
    setState(() => _paceTarget = seconds);
    unawaited(_paceStore.save(seconds));
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    _controller.recorder.setPaceTarget(_paceOn ? _paceTarget : null);
    try {
      await _controller.start();
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  void _again() {
    final old = _controller;
    setState(() => _controller = widget.controllerFactory());
    unawaited(_controller.watchIdle());
    old.dispose();
  }

  /// Fixable refusals open the system settings; a plain denial asks again.
  VoidCallback? _issueTap(RunIssue issue) => switch (issue) {
    RunIssue.deniedForever ||
    RunIssue.serviceOff => () => unawaited(widget.openSettings()),
    RunIssue.denied => () => unawaited(_controller.watchIdle()),
    _ => null,
  };

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      final c = _controller;
      final r = c.recorder;
      final blocked = c.blocked;
      final issue = _IssueButton(
        issue: r.issue,
        onTap: _issueTap(r.issue),
        size: blocked ? 96 : 24,
      );
      return PopScope(
        // A recording lives in this screen's controller: leaving would lose it.
        canPop: !c.active,
        child: Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                children: [
                  _StatusRow(
                    controller: c,
                    uploader: _uploader,
                    issue: blocked ? null : issue,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  if (blocked)
                    Expanded(child: Center(child: issue))
                  else ...[
                    Expanded(
                      flex: 4,
                      child: KeyedSubtree(
                        key: ObjectKey(c),
                        child: (widget.mapBuilder ?? _defaultMap)(
                          context,
                          r.livePoints,
                          c.position,
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Expanded(flex: 3, child: _Numbers(recorder: r)),
                    const SizedBox(height: AppSpacing.md),
                    _Controls(
                      controller: c,
                      starting: _starting,
                      paceOn: _paceOn,
                      paceTarget: _paceTarget,
                      onPaceToggle: () => setState(() => _paceOn = !_paceOn),
                      onPaceChanged: _setPaceTarget,
                      onStart: () => unawaited(_start()),
                      onAgain: _again,
                      onClose: () => Navigator.of(context).maybePop(),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    },
  );
}

Widget _defaultMap(
  BuildContext context,
  ValueListenable<List<RunPoint>> points,
  ValueListenable<LatLng?> position,
) => RunMapSlot(points: points, position: position);
