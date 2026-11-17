/// What the run foreground service does at each plugin callback, without the
/// plugin: [RunTaskHandler] is tested against a fake port, the thin adapter in
/// `run_service_isolate.dart` only forwards.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/services/run_host.dart';

/// Drives a [RunHost] from the service's lifecycle.
class RunTaskHandler {
  /// Creates a handler over [host]; [port] is the one the host was built with.
  RunTaskHandler({required this.host, required this.port});

  /// The recording's home.
  final RunHost host;

  /// Used to stop the service when it has nothing to host.
  final RunHostPort port;

  /// The service came up. A checkpoint on disk means a run is owed: resume it,
  /// whoever started the service (the OS after a kill or a reboot, or the app
  /// after a force-stop). With none, a system start has no run to serve (a
  /// stale service or a leftover boot flag), so it stops itself; an app start
  /// waits for the start command.
  Future<void> onStart({required bool startedBySystem}) async {
    final restored = await host.restoreFromStore();
    if (restored) return;
    if (startedBySystem) {
      log(
        'RunTaskHandler: the system started the run service but there is no '
        'run checkpoint -- nothing to record, so it stops itself.',
        level: 900,
      );
      await port.stopService();
    }
  }

  /// A message from the UI.
  void onReceiveData(Object data) {
    if (data is Map && data['cmd'] is String) {
      unawaited(host.handle(data));
      return;
    }
    log(
      'RunTaskHandler: ignored a message that is not a run command '
      '(${data.runtimeType}); the break service shares this channel.',
      level: 900,
    );
  }

  /// The ongoing notification was tapped.
  void onNotificationPressed() => host.notificationPressed();

  /// The service is going away: the host lets go. This never ends the run;
  /// its checkpoint stays for the next start.
  void onDestroy() => host.dispose();
}
