/// What the app does at launch about a run that may be in progress.
library;

import 'dart:developer';

import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/run_notification.dart';

/// Whether the app must open on the live run, bringing its service back if it
/// is gone.
///
/// A run is owed while its checkpoint is on disk ([owed]). The service
/// normally survives (swipe-away, kill, reboot all restart it by themselves);
/// after a force-stop it does not, and this restarts it: the service restores
/// the run from the same checkpoint. [client.start] leaves a running service
/// alone, so asking while one is up is harmless.
Future<bool> resumeRunOnLaunch({
  required Future<bool> Function() owed,
  required ForegroundRunClient client,
}) async {
  if (!await owed()) return false;
  if (!client.isSupported) return true;
  final copy = runNotificationCopy(metres: 0, movingSeconds: 0);
  final up = await client.start(
    withLocation: true,
    title: copy.title,
    text: copy.body,
  );
  if (!up) {
    log(
      'RunLaunch: a run is owed but its service would not start; the run '
      'screen opens anyway and shows the problem. Its checkpoint is kept.',
      level: 1000,
    );
  }
  return true;
}
