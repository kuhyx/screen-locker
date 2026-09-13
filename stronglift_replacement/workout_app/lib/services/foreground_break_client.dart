/// The workout screen's side of the foreground-service conversation.
library;

import 'package:workout_app/models/break_snapshot.dart';

/// Why the foreground service could not be started.
enum BreakServiceStartResult {
  /// The service is running and the notification is visible.
  started,

  /// Started, but the user denied notifications so nothing is on screen.
  startedWithoutNotification,

  /// The platform refused to start it.
  failed,

  /// This platform has no foreground services (Linux desktop, tests).
  unsupported,
}

/// The two questions the workout screen asks of a [BreakServiceStartResult].
extension BreakServiceStartResultX on BreakServiceStartResult {
  /// True when a service is now running and will hold the rest deadline.
  bool get serviceRunning =>
      this == BreakServiceStartResult.started ||
      this == BreakServiceStartResult.startedWithoutNotification;

  /// True when the user must be told the status bar will stay empty.
  bool get needsPermissionWarning =>
      this == BreakServiceStartResult.startedWithoutNotification;
}

/// Starting, feeding and stopping the workout's foreground service.
///
/// An interface so the workout screen's wiring is testable without Android,
/// and so the one file that touches `flutter_foreground_task` stays small
/// enough to review by eye.
abstract class ForegroundBreakClient {
  /// False on platforms with no foreground service — Linux desktop, and the
  /// test host. Every other method is a no-op when this is false.
  bool get isSupported;

  /// Configures the notification channel. Safe to call more than once.
  Future<void> init();

  /// True when a break service is running right now, from any past launch.
  Future<bool> isRunning();

  /// True when the app may post notifications.
  Future<bool> hasNotificationPermission();

  /// Asks for notification permission, returning whether it was granted.
  Future<bool> requestNotificationPermission();

  /// Starts the service showing [snapshot].
  Future<bool> start(BreakSnapshot snapshot);

  /// Pushes a fresh [snapshot] to the running service.
  Future<void> push(BreakSnapshot snapshot);

  /// Stops the service and removes its notification.
  Future<void> stop();

  /// Registers [onNudge], called when the service wants the queue drained.
  void listenForDrainNudges(void Function() onNudge);

  /// Unregisters the callback registered by [listenForDrainNudges].
  void stopListeningForDrainNudges();
}
