/// Pushes completed workout sessions to the shared sync backend.
library;


import 'dart:convert';
import 'dart:developer';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/sync_device_id.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/services/sync_state_factory.dart';
import 'package:workout_app/services/workout_sync_session.dart';

part 'workout_sync_service_read.dart';

const _pathPrefix = 'screen-locker-sync/devices';
const _logFilename = 'log.json';

String _encode(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

/// The outcome of a [WorkoutSyncService.push] / [WorkoutSyncService.pushManual].
///
/// A bare `Future<void>` used to hide every failure: the caller could not
/// tell "nothing to do" from "it broke", and the only trace was a
/// `debugPrint` that goes nowhere in a release build. That is the exact
/// silent-failure shape `CLAUDE.md` forbids, and it is why a workout could
/// go unpushed with nothing anywhere saying so.
@immutable
class PushResult {
  /// Creates a result. [reason] should read like a sentence a human can act on.
  const PushResult({required this.pushed, required this.reason});

  /// Whether the sync tick completed without error.
  final bool pushed;

  /// Why it did or did not happen.
  final String reason;

  @override
  String toString() => 'PushResult(pushed: $pushed, reason: $reason)';
}

/// Mirrors the PC-side `_workout_sync.py`: GitHub is used purely as dumb
/// file storage via the Contents API, one [Record] per completed session,
/// merged onto whatever this phone has already pushed.
///
/// A failed push never throws into the workout-completion flow -- sync being
/// unreachable must not cost the user their session -- but it is never
/// silent either: every path returns a [PushResult] whose `reason` says what
/// happened, and failures log at error level.
class WorkoutSyncService {
  /// Creates a [WorkoutSyncService]. [owner]/[repo]/[httpClient] default to
  /// the real `syncs` repo (`screen-locker-sync/` subdirectory) and a fresh
  /// [http.Client]; tests
  /// override them to point at an in-memory [http.testing.MockClient]
  /// instead of the real network.
  WorkoutSyncService({
    this.owner = syncRepoOwner,
    this.repo = syncRepoName,
    http.Client? httpClient,
    this.firebaseFactory,
    this.stateStore,
    // Dart forbids private named params, so this can't be an initializing
    // formal; assign it explicitly (mirrors crdt_sync_dart's GitHubClient).
    // ignore: prefer_initializing_formals
  }) : _httpClient = httpClient;

  /// Builds the Firebase backend. Injected so tests can supply a fake, or null
  /// to assert the pre-migration GitHub-only path still works.
  final Future<FirebaseRestClient?> Function()? firebaseFactory;

  /// Revision cache. Injected so tests need no application-support directory.
  final SyncStateStore? stateStore;

  /// Firebase when this device is set up for it, else null (a normal state
  /// during the cutover: sync then runs over GitHub exactly as before).
  Future<FirebaseRestClient?> _openFirebase() =>
      (firebaseFactory ?? openFirebase)();

  /// Whether this device has been set up for Firebase.
  ///
  /// Cheap on the common path: [openFirebase] reuses a cached refresh token
  /// and only signs in when there is none.
  Future<bool> _hasFirebaseAccount() async => await _openFirebase() != null;

  /// The revision cache, defaulting to a file beside the app's data.
  Future<SyncStateStore> _openStateStore() async =>
      stateStore ?? await openSyncStateStore();

  /// The repo owner/org to push to.
  final String owner;

  /// The repo name to push to.
  final String repo;
  final http.Client? _httpClient;

  /// Pushes [session] to this device's log, merging with whatever it has
  /// already pushed.
  ///
  /// Never throws: returns a [PushResult] saying whether the tick happened
  /// and why. Failures are logged at error level so an unpushed workout
  /// leaves a trace rather than vanishing.
  Future<PushResult> push(WorkoutSession session) async {
    final settings = await SyncSettings.load();
    // Either backend counts. Gating on the GitHub token alone silently
    // dropped every push from a device connected only to Firebase -- and
    // once the mirror is retired that would be every device.
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      const reason = 'sync not configured (no Firebase account, no token)';
      log('WorkoutSyncService.push skipped: $reason', level: 900);
      return const PushResult(pushed: false, reason: reason);
    }
    return _session(settings.token).run(
      operation: 'push',
      successReason: 'pushed',
      failurePrefix: 'push failed',
      addition: Record(
        id: session.startTime.toIso8601String(),
        fields: {
          'payload': (session.toJson(), Hlc.newTick(currentSyncDeviceId)),
        },
      ),
    );
  }

  /// Builds the collaborator that owns one round-trip's client lifecycle.
  WorkoutSyncSession _session(String token) => WorkoutSyncSession(
    owner: owner,
    repo: repo,
    token: token,
    pathPrefix: _pathPrefix,
    logFilename: _logFilename,
    encode: _encode,
    decode: _decode,
    openFirebaseClient: _openFirebase,
    openStateStore: _openStateStore,
    httpClient: _httpClient,
  );

  /// Runs a sync tick with no new record, purely to find out whether sync
  /// works right now.
  ///
  /// [push] and [pushManual] both need something to push, and
  /// [readMergedWorkoutPayloads] returns `const []` on failure -- it
  /// swallows the reason, so neither can answer "is this device actually
  /// talking to Firebase?". The home screen's status card needs exactly that
  /// answer, with a reason a human can act on, which is why this exists.
  ///
  /// Same never-throw, always-report contract as [push].
  Future<PushResult> syncNow() async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      const reason = 'sync not configured (no Firebase account, no token)';
      log('WorkoutSyncService.syncNow skipped: $reason', level: 900);
      return const PushResult(pushed: false, reason: reason);
    }
    // No addition: whatever this device already has, unchanged. The point is
    // the round trip, not the payload.
    return _session(settings.token).run(
      operation: 'syncNow',
      successReason: 'synced',
      failurePrefix: 'sync failed',
    );
  }


  /// Pushes a pre-built manual-workout [record] to this device's log.
  ///
  /// Same never-throw, always-report contract as [push].
  Future<PushResult> pushManual(Record record) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      const reason = 'sync not configured (no Firebase account, no token)';
      log('WorkoutSyncService.pushManual skipped: $reason', level: 900);
      return const PushResult(pushed: false, reason: reason);
    }
    return _session(settings.token).run(
      operation: 'pushManual',
      successReason: 'pushed',
      failurePrefix: 'push failed',
      addition: record,
    );
  }

  /// Returns every device's manual-workout payloads, merged and deduped by id
  /// (highest HLC wins), for computing the shared budget. Pull-only — unlike
  /// [pushManual] it never writes, so showing the budget can't mutate the repo.
  /// Returns an empty list if sync isn't configured or the repo is unreachable.
  Future<List<Map<String, dynamic>>> readMergedManualPayloads() =>
      _readMergedPayloads(kind: kManualWorkoutSyncKind);
  /// Every synced workout, whatever kind — manual, StrongLifts or RunnerUp.
  ///
  /// The PC publishes its whole `log.json` (including verified runs),
  /// so this is what the history view needs to show the SAME workouts both
  /// devices know about. Deliberately unfiltered: the manual-workout budget
  /// uses [readMergedManualPayloads] instead.
  Future<List<Map<String, dynamic>>> readMergedWorkoutPayloads() =>
      _readMergedPayloads();
  /// Whether this device has ANY sync credentials -- a GitHub token or a
  /// Firebase account.
  ///
  /// Mirrors the gate every push already applies internally, exposed so the
  /// home screen can tell "not set up" (the user must act) apart from "set
  /// up but broken" (retrying might help) without duplicating the rule.
  Future<bool> isConfigured() async {
    final settings = await SyncSettings.load();
    return settings.isConfigured || await _hasFirebaseAccount();
  }
}
