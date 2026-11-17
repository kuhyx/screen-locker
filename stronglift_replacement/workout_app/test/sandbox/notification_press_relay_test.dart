// Tapping the run notification must reach the run host, in every flavor.
//
// flutter_foreground_task 11.0.3 only calls the task handler's
// onNotificationPressed when the intent that opened the activity is MAIN +
// category LAUNCHER (ForegroundService.handleNotificationContentIntent). The
// sandbox flavor has no LAUNCHER filter (see sandbox_manifest_test.dart), so
// `getLaunchIntentForPackage` hands the notification a MAIN + INFO intent and
// the plugin silently drops the press: the app opened on the plain run screen,
// never on the finish modal. MainActivity therefore relays such presses
// itself, for the cold start (onCreate) and for a running app (onNewIntent).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Relative to the package root, which is `flutter test`'s cwd.
const _activityPath =
    'android/app/src/main/kotlin/com/kuhy/workout_app/MainActivity.kt';

void main() {
  late String activity;

  setUpAll(() => activity = File(_activityPath).readAsStringSync());

  test('the activity hands a press the plugin ignored to the plugin', () {
    expect(
      activity,
      contains('ForegroundService.handleNotificationContentIntent'),
    );
    expect(activity, contains('Intent.CATEGORY_LAUNCHER'));
    expect(activity, contains('"onNotificationPressed"'));
  });

  test('both a cold start and a running app are covered', () {
    expect(activity, contains('override fun onCreate'));
    expect(activity, contains('override fun onNewIntent'));
  });

  test('a press the plugin already handled is not relayed twice', () {
    expect(activity, contains('hasCategory(Intent.CATEGORY_LAUNCHER)'));
  });
}
