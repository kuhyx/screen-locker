/// Suite-wide setup: applied by `flutter test` to every test file below.
///
/// The test host is Linux, so every `Platform.isLinux` desktop branch runs
/// here -- including the one that stores the Firebase refresh token in
/// `~/.config/screen_locker/firebase_auth.json`, the live credential the
/// screen-locker daemon signs in with. A sign-in test once overwrote it with
/// fixture values and still passed. Each test now gets its own throwaway
/// config root instead; `desktopConfigRoot` refuses the real one under
/// `flutter test`, so a test that slipped past this fails loudly.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/desktop_config_dir.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  // Also set up front, so code that runs while tests are being declared is
  // redirected too, not only code inside a test body.
  final declarationRoot = _freshRoot();
  desktopConfigRootOverride = declarationRoot.path;
  tearDownAll(() => declarationRoot.deleteSync(recursive: true));
  setUp(() {
    final root = _freshRoot();
    desktopConfigRootOverride = root.path;
    addTearDown(() => root.deleteSync(recursive: true));
  });
  await testMain();
}

Directory _freshRoot() =>
    Directory.systemTemp.createTempSync('workout_app_test_config_');
