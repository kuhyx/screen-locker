/// What the run screen shows: a mirror of the host's last snapshot.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_wire.dart';

/// The recording as the UI sees it. The numbers belong to the host; this only
/// keeps the newest copy, so a dead screen loses nothing.
class RunView extends ChangeNotifier {
  /// Asks the host for a full copy ([RunCmd.hello]) when points were missed.
  void Function()? onNeedSync;

  /// Where the recording stands.
  RunPhase phase = RunPhase.idle;

  /// The current problem, or [RunIssue.none].
  RunIssue issue = RunIssue.none;

  /// Credited moving time in seconds.
  int seconds = 0;

  /// Credited distance in metres.
  double distanceM = 0;

  /// The pace target in seconds per kilometre, or null.
  int? paceTarget;

  /// The current pace in seconds per kilometre, once warmed up.
  double? pace;

  /// Where [pace] stands against [paceTarget].
  PaceBand? band;

  /// The reason the host suggests finishing, or null.
  String? suggestion;

  /// The notification was tapped while a suggestion stood: show the modal.
  bool promptFinish = false;

  /// The host is writing the finished run.
  bool saving = false;

  /// The host is through with the finished run (saved, or nothing to save).
  bool done = false;

  /// What saving did, once the host finished.
  ({bool stored, String reason})? saved;

  /// Whether any snapshot has arrived yet.
  bool synced = false;

  /// Accepted points so far, for the live map.
  final livePoints = ValueNotifier<List<RunPoint>>(const []);

  /// Folds an access check in while idle: a refusal becomes the issue, a
  /// grant clears it. Local: with no run there is no host to ask.
  void noteAccess(LocationAccess access) {
    if (phase != RunPhase.idle) return;
    if (!access.isGranted) {
      issue = RunIssue.forAccess(access);
      return notifyListeners();
    }
    if (!issue.isAccess) return;
    issue = RunIssue.none;
    notifyListeners();
  }

  /// Takes the host's newest message.
  void apply(Map<Object?, Object?> m) {
    final next = RunPhase.values.byName(m['phase']! as String);
    final incoming = RunIssue.values.byName(m['issue']! as String);
    // An idle host knows nothing of the permission the UI just checked: its
    // "no issue" must not wipe a refusal the UI found itself.
    if (next != RunPhase.idle || incoming != RunIssue.none) issue = incoming;
    phase = next;
    seconds = m['seconds']! as int;
    distanceM = (m['distanceM']! as num).toDouble();
    paceTarget = m['paceTarget'] as int?;
    pace = (m['pace'] as num?)?.toDouble();
    final bandName = m['band'] as String?;
    band = bandName == null ? null : PaceBand.values.byName(bandName);
    suggestion = m['suggestion'] as String?;
    promptFinish = m['prompt']! as bool;
    saving = m['saving']! as bool;
    done = m['done']! as bool;
    final savedRaw = m['saved'] as Map<Object?, Object?>?;
    saved = savedRaw == null
        ? null
        : (
            stored: savedRaw['stored']! as bool,
            reason: savedRaw['reason']! as String,
          );
    synced = true;
    _applyPoints(m);
    notifyListeners();
  }

  void _applyPoints(Map<Object?, Object?> m) {
    final from = m['from']! as int;
    final total = m['total']! as int;
    final fresh = [
      for (final raw in m['pts']! as List<Object?>)
        decodePoint((raw! as List<Object?>).cast<Object?>()),
    ];
    final held = livePoints.value;
    if (from == 0) {
      livePoints.value = fresh;
    } else if (from == held.length) {
      livePoints.value = [...held, ...fresh];
    } else {
      // A message was lost (the screen was away): ask for everything again.
      onNeedSync?.call();
      return;
    }
    if (livePoints.value.length != total) onNeedSync?.call();
  }

  @override
  void dispose() {
    livePoints.dispose();
    super.dispose();
  }
}
