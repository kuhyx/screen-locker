/// Carries progression state and the in-progress session through Firebase.
///
/// `backup.json` on external storage survives an uninstall, but only while the
/// user grants storage permission — deny it and a reinstall lands on factory
/// defaults with months of progression gone. This module gives the same data a
/// second, permission-free home so the app simply *has* its state after a
/// reinstall rather than needing a backfill.
///
/// ## Why these paths sit OUTSIDE `devices/`
///
/// Records live at `screen-locker-sync/exercise_state/<exercise name>` and
/// `screen-locker-sync/active_session`, as siblings of `devices/` rather than
/// inside it. Two independent reasons:
///
/// * **Keyed on exercise name, not device.** A reinstall mints a new
///   per-install uuid ([currentSyncDeviceId]), so a per-device copy would be
///   orphaned by the very event this exists to survive.
/// * **Structurally invisible to the workout readers.** The PC's
///   `_workout_sync.py` and this app's [WorkoutSyncService] each list exactly
///   one prefix — `screen-locker-sync/devices` — and read `<id>/log.json`
///   underneath it. Nothing lists the bare `screen-locker-sync` prefix, so a
///   progression record cannot be enumerated as a workout, let alone mistaken
///   for one. That matters because a progression record miscounted as a session
///   would silently hand out unlock credit for a workout nobody did.
library;

import 'dart:convert';
import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_device_id.dart';

part 'progression_sync_service_pull.dart';
part 'progression_sync_service_push.dart';
part 'progression_sync_service_session.dart';

/// Root for everything this module owns. Deliberately NOT under `devices/`.
const kProgressionPrefix = 'screen-locker-sync/exercise_state';

/// Path of the single shared in-progress session.
const kActiveSessionPath = 'screen-locker-sync/active_session';

const _payloadField = 'payload';

/// The outcome of a progression sync tick.
///
/// Mirrors `WorkoutSyncService.PushResult`: never throw into the workout flow,
/// but never fail silently either — [reason] should read like a sentence a
/// human can act on.
class ProgressionSyncResult {
  /// Creates a result.
  const ProgressionSyncResult({
    required this.changed,
    required this.reason,
    this.count = 0,
  });

  /// Whether anything was actually written or applied.
  final bool changed;

  /// How many exercise records were involved.
  final int count;

  /// Why it did or did not happen.
  final String reason;

  @override
  String toString() =>
      'ProgressionSyncResult(changed: $changed, count: $count, '
      'reason: $reason)';
}

/// Pushes and pulls progression state + the active session over Firebase.
class ProgressionSyncService {
  /// Creates a service. [firebaseFactory] is injected so tests can supply a
  /// fake without reaching the OS keystore.
  ProgressionSyncService({this.firebaseFactory});

  /// Builds the Firebase backend, or null when this device is not set up.
  final Future<FirebaseRestClient?> Function()? firebaseFactory;

  Future<FirebaseRestClient?> _openFirebase() =>
      (firebaseFactory ?? openFirebase)();

  /// Every exercise across both plans, by name.
  static Map<String, Exercise> get _defaults => {
    for (final ex in [...workoutA, ...workoutB]) ex.name: ex,
  };

  static Map<String, dynamic> _stateToJson(ExerciseState s) => {
    'name': s.name,
    'weight': s.weight,
    'reps': s.reps,
    'success_streak': s.successStreak,
    'fail_streak': s.failStreak,
    'max_weight': s.maxWeight,
    'success_threshold': s.successThreshold,
    'fail_threshold': s.failThreshold,
  };

  static ExerciseState _stateFromJson(Map<String, dynamic> j) => ExerciseState(
    name: j['name']! as String,
    weight: (j['weight']! as num).toDouble(),
    reps: (j['reps']! as num).toInt(),
    successStreak: (j['success_streak'] as num?)?.toInt() ?? 0,
    failStreak: (j['fail_streak'] as num?)?.toInt() ?? 0,
    maxWeight: (j['max_weight']! as num).toDouble(),
    successThreshold: (j['success_threshold'] as num?)?.toInt() ?? 3,
    failThreshold: (j['fail_threshold'] as num?)?.toInt() ?? 2,
  );

  /// The remote path holding [name]'s progression record.
  ///
  /// The name is used raw on purpose: [FirebaseRestClient] escapes every path
  /// segment with `encodeKey` before building the URI, so the characters
  /// Realtime Database forbids in a key (`.`, `#`, `$`, `[`, `]`) are already
  /// handled. Encoding here as well would double-escape and write to a
  /// different key than [listDirectory] reports.
  static String pathForExercise(String name) => '$kProgressionPrefix/$name';

  /// Whether Firebase already holds a progression record for ANY of [states].
  ///
  /// Any single one is enough to prove this account has real progression
  /// stored, which is all the caller needs to decide not to overwrite it.
  Future<bool> _remoteHasAnyProgression(
    FirebaseRestClient client,
    List<ExerciseState> states,
  ) async {
    for (final state in states) {
      if (await _readRecord(client, pathForExercise(state.name)) != null) {
        return true;
      }
    }
    return false;
  }

  /// Reads one remote record, returning its payload and HLC.
  ///
  /// Returns null when absent. A malformed record is reported at error level
  /// and treated as absent rather than crashing the caller.
  Future<(Map<String, dynamic>, Hlc)?> _readRecord(
    FirebaseRestClient client,
    String path,
  ) async {
    final text = await client.getFileText(path);
    if (text == null) return null;
    try {
      final record = Record.fromJson(
        jsonDecode(text) as Map<String, dynamic>,
      );
      final field = record.fields[_payloadField];
      if (field == null) return null;
      final payload = field.$1;
      if (payload is! Map) return null;
      return (payload.cast<String, dynamic>(), field.$2);
    } on Object catch (error, stackTrace) {
      log(
        'ProgressionSyncService: corrupt record at $path — treating as absent',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  Future<void> _writeRecord(
    FirebaseRestClient client,
    String path,
    String id,
    Map<String, dynamic> payload,
    Hlc hlc,
  ) async {
    final record = Record(id: id, fields: {_payloadField: (payload, hlc)});
    await client.putFileText(
      path,
      jsonEncode(record.toJson()),
      // Ignored by the Realtime Database backend (no commit log), but the
      // interface requires it and a GitHub-backed store would surface it.
      message: 'progression: $id',
    );
  }
}
