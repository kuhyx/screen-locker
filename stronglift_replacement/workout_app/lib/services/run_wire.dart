/// The messages the run UI and the run host (the foreground-service isolate)
/// exchange. JSON-safe maps only: they cross an isolate boundary.
library;

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_engine.dart';

/// Key every host message carries, so the break service's data channel (the
/// same plugin channel) can tell the two apart.
const kRunWireKey = 'run';

/// UI -> host commands, under the `cmd` key.
abstract final class RunCmd {
  /// "Send me everything": answered with a full snapshot.
  static const hello = 'hello';

  /// Begin recording; carries `paceTarget` and `sound`.
  static const start = 'start';

  /// Pause crediting.
  static const pause = 'pause';

  /// Resume crediting.
  static const resume = 'resume';

  /// End the run (only after the confirm modal).
  static const finish = 'finish';

  /// Change the pace target; carries `paceTarget`.
  static const paceTarget = 'paceTarget';

  /// The UI showed the finish modal the notification asked for.
  static const ackPrompt = 'ackPrompt';
}

/// One point as `[ms, lat, lon, distanceM, altitudeM?]`.
List<Object?> encodePoint(RunPoint p) => [
  p.time.millisecondsSinceEpoch,
  p.latitude,
  p.longitude,
  p.distanceM,
  p.altitudeM,
];

/// Inverse of [encodePoint].
RunPoint decodePoint(List<Object?> raw) => RunPoint(
  time: DateTime.fromMillisecondsSinceEpoch(raw[0]! as int, isUtc: true),
  latitude: (raw[1]! as num).toDouble(),
  longitude: (raw[2]! as num).toDouble(),
  distanceM: (raw[3]! as num).toDouble(),
  altitudeM: (raw[4] as num?)?.toDouble(),
);

/// The host's state as one message.
///
/// [from] says which point index `pts` starts at, so a UI that already holds
/// the first [from] points appends, and one that does not sends
/// [RunCmd.hello] for a full copy.
Map<String, Object?> encodeSnapshot(
  RunEngine engine, {
  required int from,
  String? suggestion,
  bool prompt = false,
  bool saving = false,
  bool done = false,
  ({bool stored, String reason})? saved,
}) {
  final points = engine.points;
  return {
    kRunWireKey: 1,
    'phase': engine.phase.name,
    'issue': engine.issue.name,
    'seconds': engine.seconds,
    'distanceM': engine.distanceM,
    'paceTarget': engine.paceTarget,
    'pace': engine.pace,
    'band': engine.band?.name,
    'suggestion': suggestion,
    'prompt': prompt,
    'saving': saving,
    'done': done,
    'saved': saved == null
        ? null
        : {'stored': saved.stored, 'reason': saved.reason},
    'from': from,
    'total': points.length,
    'pts': [for (var i = from; i < points.length; i++) encodePoint(points[i])],
  };
}

/// Whether [data] is a host message (not a break-service one).
bool isRunMessage(Object? data) => data is Map && data[kRunWireKey] == 1;
