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

  /// Pushes local progression to Firebase, one record per exercise.
  ///
  /// Each record carries an HLC derived from the remote one it replaces
  /// (`previous:`), so the stamps form a causal chain per exercise rather than
  /// depending on device clocks agreeing.
  ///
  /// Refuses to push at all from a freshly-installed database that still has
  /// remote records to lose. Without that, the seed-then-push sequence a
  /// reinstall performs would overwrite real progression with factory defaults
  /// and leave Firebase as the only — wrong — copy. The test is
  /// [StorageService.looksFreshlyInstalled], not a per-exercise value
  /// comparison: a deliberate [StorageService.resetExerciseToDefaults] can
  /// produce a row identical to a seeded one, and that reset must still sync.
  Future<ProgressionSyncResult> pushProgression() async {
    final client = await _openFirebase();
    if (client == null) {
      const reason =
          'progression NOT pushed: no Firebase account on this device — '
          'connect one in Settings, or progression lives only on this phone';
      log(
        'ProgressionSyncService.pushProgression skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      final states = await StorageService.instance.getAllExerciseStates();

      // Decided ONCE, before any write. Evaluating this per exercise would
      // still write every record Firebase happens not to hold yet before
      // hitting the first one it does — a fresh install would leak factory
      // defaults for exactly the exercises with no remote copy to protect them.
      //
      // Gated on hasSyncedProgression, NOT looksFreshlyInstalled: the only
      // production caller finishes a workout (writing history and
      // last_workout_type) before pushing, so a freshness test would already
      // be false here and could never fire.
      if (!await StorageService.instance.hasSyncedProgression() &&
          await _remoteHasAnyProgression(client, states)) {
        const reason =
            'progression NOT pushed: this install has never pulled from '
            'Firebase, but Firebase already holds progression. Refusing to '
            'overwrite it with local state that may be factory defaults — '
            'restart the app (or reconnect sync) so the real state is pulled '
            'down first.';
        log('ProgressionSyncService: $reason', level: 1000);
        return const ProgressionSyncResult(changed: false, reason: reason);
      }

      var written = 0;
      for (final state in states) {
        final path = pathForExercise(state.name);
        final remote = await _readRecord(client, path);

        await _writeRecord(
          client,
          path,
          'exercise_state:${state.name}',
          _stateToJson(state),
          // Chain from the record being replaced so the stamp is causal, not
          // merely wall-clock: an offline device cannot mint a "newer" tick
          // just by having a fast clock.
          Hlc.newTick(currentSyncDeviceId, previous: remote?.$2),
        );
        written++;
      }
      return ProgressionSyncResult(
        changed: written > 0,
        count: written,
        reason: 'pushed $written exercise(s) to Firebase',
      );
    } on Object catch (error, stackTrace) {
      // Deliberately broad and swallowed: a sync failure must never cost the
      // user their workout. Never silent, though — this logs at error level
      // and the reason travels back to the caller.
      final reason = 'progression push failed: $error';
      log(
        'ProgressionSyncService.pushProgression failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return ProgressionSyncResult(changed: false, reason: reason);
    } finally {
      client.close();
    }
  }

  /// Pulls remote progression into the local DB.
  ///
  /// Applies only to a freshly-installed database
  /// ([StorageService.looksFreshlyInstalled]) — so a pull can restore a wiped
  /// install but can never clobber progression, or a deliberate reset, made on
  /// this phone. That keeps the operation safe to run unconditionally at app
  /// start.
  Future<ProgressionSyncResult> pullProgression() async {
    final client = await _openFirebase();
    if (client == null) {
      const reason =
          'progression NOT pulled: no Firebase account on this device — '
          'connect one in Settings to restore progression without storage '
          'permission';
      log(
        'ProgressionSyncService.pullProgression skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      // Once this install has reconciled with Firebase, local state wins.
      // Checked instead of looksFreshlyInstalled because a hand edit
      // (setExerciseWeight, resetExerciseToDefaults) writes neither history
      // nor last_workout_type: the DB still "looks fresh" afterwards, so a
      // freshness test would silently revert the user's own change on the very
      // next launch.
      if (await StorageService.instance.hasSyncedProgression()) {
        const reason =
            'progression NOT pulled: this install has already reconciled with '
            'Firebase, so local state wins and must not be overwritten';
        log('ProgressionSyncService: $reason', level: 800);
        return const ProgressionSyncResult(changed: false, reason: reason);
      }

      var applied = 0;
      for (final name in _defaults.keys) {
        final remote = await _readRecord(client, pathForExercise(name));
        if (remote == null) continue;
        await StorageService.instance.replaceExerciseState(
          _stateFromJson(remote.$1),
        );
        applied++;
      }
      // Marked even when nothing came down: reaching the backend and finding
      // it empty IS a successful reconcile, and it is what unblocks this
      // device's first push. Only a thrown error leaves the flag unset.
      await StorageService.instance.markProgressionSynced();
      final reason = applied == 0
          ? 'no progression restored: Firebase holds no exercise records yet'
          : 'restored $applied exercise(s) from Firebase';
      log('ProgressionSyncService.pullProgression: $reason', level: 800);
      return ProgressionSyncResult(
        changed: applied > 0,
        count: applied,
        reason: reason,
      );
    } on Object catch (error, stackTrace) {
      final reason = 'progression pull failed: $error';
      log(
        'ProgressionSyncService.pullProgression failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return ProgressionSyncResult(changed: false, reason: reason);
    } finally {
      client.close();
    }
  }

  /// Publishes the in-progress session, or clears it when [data] is null.
  ///
  /// Called on set completion rather than per rep. `saveActiveSession` fires on
  /// every tap, and a Firebase write per tap is exactly the traffic the sync
  /// revision cache exists to avoid.
  Future<ProgressionSyncResult> pushActiveSession(
    Map<String, dynamic>? data,
  ) async {
    final client = await _openFirebase();
    if (client == null) {
      const reason = 'active session NOT pushed: no Firebase account';
      log(
        'ProgressionSyncService.pushActiveSession skipped: $reason',
        level: 900,
      );
      return const ProgressionSyncResult(changed: false, reason: reason);
    }

    try {
      if (data == null) {
        // An empty object, not a delete: the readers treat absent and empty
        // alike, and a write keeps the HLC ordering intact for the next push.
        await _writeRecord(
          client,
          kActiveSessionPath,
          'active_session',
          const {},
          Hlc.newTick(currentSyncDeviceId),
        );
        return const ProgressionSyncResult(
          changed: true,
          reason: 'cleared the shared active session',
        );
      }
      await _writeRecord(
        client,
        kActiveSessionPath,
        'active_session',
        data,
        Hlc.newTick(currentSyncDeviceId),
      );
      return const ProgressionSyncResult(
        changed: true,
        reason: 'published the active session',
      );
    } on Object catch (error, stackTrace) {
      final reason = 'active session push failed: $error';
      log(
        'ProgressionSyncService.pushActiveSession failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return ProgressionSyncResult(changed: false, reason: reason);
    } finally {
      client.close();
    }
  }

  /// Returns the shared in-progress session, or null when there is none.
  ///
  /// An empty payload means "explicitly cleared" and reads back as null, so a
  /// finished workout is never resurrected.
  Future<Map<String, dynamic>?> readActiveSession() async {
    final client = await _openFirebase();
    if (client == null) {
      log(
        'ProgressionSyncService.readActiveSession skipped: no Firebase account',
        level: 900,
      );
      return null;
    }
    try {
      final remote = await _readRecord(client, kActiveSessionPath);
      if (remote == null || remote.$1.isEmpty) return null;
      return remote.$1;
    } on Object catch (error, stackTrace) {
      log(
        'ProgressionSyncService.readActiveSession failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    } finally {
      client.close();
    }
  }
}
