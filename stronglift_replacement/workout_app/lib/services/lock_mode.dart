/// Whether this process is acting as the screen lock.
///
/// The Linux runner takes the X grab and drops the window decorations when
/// `--lock-mode` is passed (see `linux/runner/my_application.cc`); this is the
/// Dart half, which removes the ways *out* of the app. Both halves read the
/// same argument so they can never disagree about which mode is live.
///
/// The distinction matters because a lock the user can dismiss is not a lock:
/// with enforcement armed, leaving the workout early has to be impossible
/// rather than merely discouraged.
library;

/// True when the process was started with `--lock-mode`.
///
/// Set once from `main()`; defaults to false so every test and the ordinary
/// windowed launch behave exactly as before.
bool lockModeEnabled = false;

/// The flag the runner and the Dart side agree on.
const String kLockModeFlag = '--lock-mode';

/// Returns whether [args] requests lock mode.
bool parseLockMode(List<String> args) => args.contains(kLockModeFlag);
