/// Where the Linux desktop build keeps its per-app config (`~/.config`).
///
/// Every desktop path this app reads or writes under the user's home goes
/// through [desktopConfigRoot]: the shared Firebase refresh token in
/// `screen_locker/firebase_auth.json` and the account in `crdt-sync/`.
///
/// It exists as one choke point because `flutter test` runs on a Linux host,
/// so `Platform.isLinux` is true there too. Before this seam, a sign-in test
/// that stored its fixture refresh token wrote it straight over the live
/// credential the screen-locker daemon signs in with.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

/// Replaces `$HOME/.config` for the rest of the process when non-null.
///
/// `test/flutter_test_config.dart` points it at a temp directory for every
/// test file; nothing in the app sets it.
@visibleForTesting
String? desktopConfigRootOverride;

/// Returns the config root (`$HOME/.config`), or null when HOME is unset.
///
/// Throws [StateError] under `flutter test` (which exports `FLUTTER_TEST`)
/// when the root would be the real `$HOME/.config` or anywhere inside it: a
/// test that got here without the temp-dir override would otherwise read the
/// real account and overwrite the real refresh token, and still pass.
/// [environment] defaults to [Platform.environment]; tests pass their own.
String? desktopConfigRoot({Map<String, String>? environment}) {
  final env = environment ?? Platform.environment;
  final home = env['HOME'];
  final realRoot = (home == null || home.isEmpty)
      ? null
      : p.join(home, '.config');
  final root = desktopConfigRootOverride ?? realRoot;
  if (env.containsKey('FLUTTER_TEST') && realRoot != null && root != null) {
    if (p.equals(root, realRoot) || p.isWithin(realRoot, root)) {
      throw StateError(
        'Refusing to use the real $realRoot under flutter test: that is the '
        'live desktop credential store. Set desktopConfigRootOverride to a '
        'temp directory (test/flutter_test_config.dart does this for every '
        'test file).',
      );
    }
  }
  return root;
}
