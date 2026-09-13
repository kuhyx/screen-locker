// The two plugin-backed implementations are almost entirely `coverage:ignore`d
// -- every method body is a platform-channel call that cannot run on the test
// host. Their CONSTRUCTORS are deliberately outside those blocks, and this file
// exists to execute them: that gives each file a genuinely-hit line in
// lcov.info, so `check_flutter_coverage.sh`'s "every lib file must appear"
// guard is satisfied by real coverage rather than by an empty record.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/break_service_port.dart';
import 'package:workout_app/services/break_service_port_flutter.dart';
import 'package:workout_app/services/foreground_break_client.dart';
import 'package:workout_app/services/foreground_break_client_flutter.dart';

void main() {
  test('the service-isolate port can be constructed', () {
    expect(FlutterBreakServicePort(), isNotNull);
  });

  test('the UI-side client can be constructed', () {
    final client = FlutterForegroundBreakClient();
    expect(client, isNotNull);
    // Linux test host: there is no foreground service here, which is exactly
    // why every other method on this class is unreachable from a test.
    expect(client.isSupported, isFalse);
  });

  test('the alert channel id is versioned', () {
    // Android freezes a channel's sound and importance on first creation, so
    // a wrong setting can only ever be fixed by moving to a new id.
    expect(kBreakEndChannelId, endsWith('_v1'));
    expect(kWorkoutOngoingChannelId, endsWith('_v1'));
    expect(kBreakEndNotificationId, isNot(kWorkoutDoneNotificationId));
  });

  test('the three button ids are distinct and in display order', () {
    // Android allows at most three action buttons, which is why Done records
    // the full target and − 1 rep walks down from there: rep targets run from
    // 5 to 30 across the plan, so a button per count is impossible.
    expect(BreakNotificationAction.inButtonOrder, [
      BreakNotificationAction.done,
      BreakNotificationAction.minusRep,
      BreakNotificationAction.skipBreak,
    ]);
    expect(BreakNotificationAction.inButtonOrder.toSet(), hasLength(3));
  });

  test('start results answer the two questions the screen asks', () {
    expect(BreakServiceStartResult.started.serviceRunning, isTrue);
    expect(
      BreakServiceStartResult.startedWithoutNotification.serviceRunning,
      isTrue,
      reason: 'the isolate still holds the wake lock and still plays the cue',
    );
    expect(BreakServiceStartResult.failed.serviceRunning, isFalse);
    expect(BreakServiceStartResult.unsupported.serviceRunning, isFalse);

    expect(
      BreakServiceStartResult.startedWithoutNotification
          .needsPermissionWarning,
      isTrue,
    );
    for (final other in [
      BreakServiceStartResult.started,
      BreakServiceStartResult.failed,
      BreakServiceStartResult.unsupported,
    ]) {
      expect(other.needsPermissionWarning, isFalse);
    }
  });
}
