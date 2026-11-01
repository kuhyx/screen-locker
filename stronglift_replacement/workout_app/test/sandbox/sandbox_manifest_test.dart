// The sandbox flavor is hidden from the launcher, which removes the only
// intent filter `getLaunchIntentForPackage` used to find. flutter_foreground_task
// builds its notification from that intent; null made `startForeground` throw,
// so Android killed the app with ForegroundServiceDidNotStartInTimeException.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Relative to the package root, which is `flutter test`'s cwd.
const _manifestPath = 'android/app/src/sandbox/AndroidManifest.xml';

void main() {
  late String manifest;

  setUpAll(() => manifest = File(_manifestPath).readAsStringSync());

  test('the sandbox stays out of the launcher', () {
    expect(
      manifest,
      matches(
        RegExp(
          r'category\s+android:name="android\.intent\.category\.LAUNCHER"'
          r'\s+tools:node="remove"',
        ),
      ),
    );
  });

  test('a MAIN + INFO filter keeps the package launchable by intent', () {
    final filters = RegExp(r'<intent-filter>(.*?)</intent-filter>', dotAll: true)
        .allMatches(manifest)
        .map((m) => m.group(1)!);
    expect(
      filters.where(
        (f) =>
            f.contains('android.intent.action.MAIN') &&
            f.contains('android.intent.category.INFO'),
      ),
      isNotEmpty,
    );
  });
}
