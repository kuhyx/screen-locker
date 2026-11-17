/// The recorder's log lines, kept apart so the state machine stays short.
///
/// Level 1000 is "something is wrong and the user must act or lose data";
/// 900 is a warning. Nothing here is silent: see the repo's
/// "NEVER fail silently" rule.
library;

import 'dart:developer';

import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// Recording was refused because location access is [access].
void logRefused(LocationAccess access) {
  final fix = access == LocationAccess.serviceOff
      ? 'Switch location on'
      : 'Grant location to the app in system settings';
  log(
    'RunRecorder: not recording -- location access is ${access.name}. '
    '$fix and start again.',
    level: 1000,
  );
}

/// A fix was dropped for [verdict]; the caller says it once per kind.
void logDropped(FixVerdict verdict) => log(
  'RunRecorder: dropped a GPS fix (${verdict.name}); further drops of '
  'this kind are not logged. Mock fixes never count towards a run.',
  level: 900,
);

/// The location stream reported [error].
void logStreamError(Object error, StackTrace stack) => log(
  'RunRecorder: the location stream failed ($error) -- fixes may have '
  'stopped; time and distance are not crediting until they resume.',
  level: 1000,
  error: error,
  stackTrace: stack,
);

/// The location stream ended while a run was still active.
void logStreamEnded() => log(
  'RunRecorder: the location stream ended while still recording; '
  'finish the run to save what was captured.',
  level: 900,
);

/// A run finished with [count] usable fixes, too few to save.
void logTooShort(int count) => log(
  'RunRecorder: finished with $count usable GPS fix(es) '
  '-- not enough for a track, so nothing is saved.',
  level: 1000,
);

/// Restoring the checkpointed run failed with [error].
void logRestoreFailed(Object error, StackTrace stack) => log(
  'RunRecorder: could not reopen the position source to restore the run '
  '($error) -- the run stays unrecovered; its checkpoint is kept.',
  level: 1000,
  error: error,
  stackTrace: stack,
);
