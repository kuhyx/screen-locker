/// The live run/walk screen: sport, start/pause/finish, and big numbers.
///
/// One screen, no scrolling (R7), and no words (textgate): icons, colours and
/// digits only. Icons that report a problem are tappable where the fix is in
/// system settings.
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/foreground_run_client_flutter.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map_slot.dart';
import 'package:workout_app/widgets/run_upload_badge.dart';

part 'run_screen_parts.dart';

/// The controller the app uses: real GPS (or the sandbox replay), the real
/// foreground service, the real database and the app-wide upload queue.
RunController buildRunController() => RunController(
  sourceFor: positionSourceFor,
  service: FlutterForegroundRunClient(),
  cues: FeedbackCues(AudioPlayer()),
  save: (track) => saveRecordedRun(
    track,
    storage: StorageService.instance,
    enqueue: RunUploader.instance.uploadPending,
  ),
);

/// Records one run or walk.
class RunScreen extends StatefulWidget {
  /// Creates the screen; every argument is a test or map seam.
  const RunScreen({
    super.key,
    this.controllerFactory = buildRunController,
    this.uploader,
    this.mapBuilder,
    this.openSettings = openAppSettings,
  });

  /// Builds the controller for a recording (called again for "new run").
  final RunController Function() controllerFactory;

  /// The upload queue shown in the badge; defaults to the app-wide one.
  final RunUploader? uploader;

  /// Builds the live map from the run's accepted points; defaults to the
  /// [RunMapSlot] placeholder. This is where the map widget goes.
  final Widget Function(BuildContext, ValueListenable<List<RunPoint>>)?
  mapBuilder;

  /// Opens the system settings page for this app.
  final Future<bool> Function() openSettings;

  @override
  State<RunScreen> createState() => _RunScreenState();
}

class _RunScreenState extends State<RunScreen> {
  late RunController _controller = widget.controllerFactory();
  late final RunUploader _uploader = widget.uploader ?? RunUploader.instance;
  bool _starting = false;

  @override
  void initState() {
    super.initState();
    SandboxLog.event('open run');
    // So the badge shows the real queue, not the pre-first-pass default.
    unawaited(_uploader.uploadPending());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      await _controller.start();
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  void _again() {
    final old = _controller;
    setState(() => _controller = widget.controllerFactory());
    old.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      final c = _controller;
      final r = c.recorder;
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
                    openSettings: widget.openSettings,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Expanded(
                    flex: 4,
                    child:
                        widget.mapBuilder?.call(context, r.livePoints) ??
                        RunMapSlot(points: r.livePoints),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Expanded(flex: 3, child: _Numbers(recorder: r)),
                  const SizedBox(height: AppSpacing.md),
                  _Controls(
                    controller: c,
                    starting: _starting,
                    onStart: () => unawaited(_start()),
                    onAgain: _again,
                    onClose: () => Navigator.of(context).maybePop(),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    },
  );
}
