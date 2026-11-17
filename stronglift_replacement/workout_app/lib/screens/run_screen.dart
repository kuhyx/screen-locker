/// The live run screen: map, big numbers, pace target, start/pause/finish.
///
/// One screen, no scrolling (R7), and no words (textgate): icons, colours and
/// digits only. Icons that report a problem are tappable where the fix is in
/// system settings. With location refused there is no map and no start, only
/// the red problem icon; coming back from settings with a grant recovers it.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'package:material_ui/material_ui.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/pace_target_store.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/services/run_view.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_finish_dialog.dart';
import 'package:workout_app/widgets/run_map_slot.dart';
import 'package:workout_app/widgets/run_pace_picker.dart';
import 'package:workout_app/widgets/run_upload_badge.dart';

part 'run_screen_numbers.dart';
part 'run_screen_parts.dart';
part 'run_screen_pulse.dart';
part 'run_screen_state.dart';

/// Builds the live map from the run's accepted points and the user's current
/// position (shown until the run has points).
typedef RunMapBuilder =
    Widget Function(
      BuildContext context,
      ValueListenable<List<RunPoint>> points,
      ValueListenable<LatLng?> position,
    );

/// Records one GPS activity (always a run).
///
/// The run itself lives in a host that outlasts this screen: leaving, closing
/// the app or replacing this screen never ends it. Only the finish button
/// followed by its confirm modal does.
class RunScreen extends StatefulWidget {
  /// Creates the screen; every argument is a test or map seam.
  const RunScreen({
    super.key,
    this.controllerFactory,
    this.uploader,
    this.paceStore,
    this.mapBuilder,
    this.openSettings = openAppSettings,
    this.resuming = false,
  });

  /// The factory `main` installs: real GPS, the real service and database.
  /// Set once at startup; tests pass [controllerFactory] instead.
  static RunController Function()? defaultControllerFactory;

  /// Builds the controller for a recording (called again for "new run").
  /// Defaults to [defaultControllerFactory].
  final RunController Function()? controllerFactory;

  /// The upload queue shown in the badge; defaults to the app-wide one.
  final RunUploader? uploader;

  /// Where the last pace target is kept; defaults to shared_preferences.
  final PaceTargetStore? paceStore;

  /// Builds the live map; defaults to [RunMapSlot].
  final RunMapBuilder? mapBuilder;

  /// Opens the system settings page for this app.
  final Future<bool> Function() openSettings;

  /// The app opened because a run is in progress: back does nothing until
  /// the host has answered and the run is on screen.
  final bool resuming;

  @override
  State<RunScreen> createState() => _RunScreenState();
}

Widget _defaultMap(
  BuildContext context,
  ValueListenable<List<RunPoint>> points,
  ValueListenable<LatLng?> position,
) => RunMapSlot(points: points, position: position);
