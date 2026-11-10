/// A [PositionSource] that replays a fixed list of fixes.
///
/// For widget and recorder tests and for the sandbox flavor's replayed run:
/// no plugin, no permission prompt, deterministic.
library;

import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// Emits [script] once, in order, then closes the stream.
class ScriptedPositionSource implements PositionSource {
  /// Creates a source that answers [access] and replays [script].
  ///
  /// With [fixDelay] set, each fix is emitted that long after the previous
  /// one (a real-time replay); otherwise they arrive back to back.
  ScriptedPositionSource(
    this.script, {
    this.access = LocationAccess.granted,
    this.fixDelay,
  });

  /// The fixes to replay.
  final List<GpsFix> script;

  /// What [requestAccess] answers.
  final LocationAccess access;

  /// Pause before each fix, or null for none.
  final Duration? fixDelay;

  @override
  Future<LocationAccess> requestAccess() async => access;

  @override
  Future<LocationAccess> checkAccess() async => access;

  @override
  Stream<GpsFix> fixes({
    Duration interval = const Duration(seconds: 2),
  }) async* {
    for (final fix in script) {
      if (fixDelay != null) await Future<void>.delayed(fixDelay!);
      yield fix;
    }
  }
}
