/// The run screen's side of the foreground-service conversation.
library;

/// What the foreground service did when a recording asked for it.
enum RunServiceState {
  /// Not started yet (or stopped).
  none,

  /// Running with its notification visible.
  running,

  /// Running, but the user denied notifications so nothing is on screen.
  runningHidden,

  /// The platform refused to start it: GPS may stop with the screen off.
  failed,

  /// This platform has no foreground services (Linux desktop, tests).
  unsupported;

  /// True while a service is up, notification shown or not.
  bool get isUp => this == running || this == runningHidden;
}

/// Starting, feeding and stopping the recording's foreground service.
///
/// The GPS stream itself stays in the UI isolate (the recorder writes to the
/// database, which only that isolate may do); the service holds the process,
/// the wake lock and the notification so the stream keeps flowing with the
/// screen off. An interface so the controller is testable without Android,
/// and so the one file that touches `flutter_foreground_task` stays small.
abstract class ForegroundRunClient {
  /// False on platforms with no foreground service.
  bool get isSupported;

  /// True when the app may post notifications.
  Future<bool> hasNotificationPermission();

  /// Asks for notification permission, returning whether it was granted.
  Future<bool> requestNotificationPermission();

  /// Starts the service showing [title] and [text]. [withLocation] adds the
  /// `location` service type, which Android 14 only allows once the location
  /// permission is held (the sandbox's replayed GPS has none, so it asks for
  /// the data-sync type alone).
  Future<bool> start({
    required bool withLocation,
    required String title,
    required String text,
  });

  /// Redraws the notification.
  Future<void> update({required String title, required String text});

  /// Stops the service and removes its notification.
  Future<void> stop();
}
