/// One sync round-trip: open the backends, merge a log, close them again.
library;

import 'dart:async';
import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/services/sync_device_id.dart';
import 'package:workout_app/services/workout_sync_service.dart';

/// Runs a single sync tick against GitHub, Firebase, or both.
///
/// `push`, `pushManual` and `syncNow` on [WorkoutSyncService] were three
/// near-identical bodies: the same configured-or-bail guard, the same
/// GitHub/Firebase/[MirrorStore] construction, the same try/catch/finally, and
/// the same never-throw-always-report contract. Only the log they submit and
/// the success wording differed.
///
/// This is a collaborator the service delegates to rather than a `part`
/// extension, deliberately. Test fakes bind to `push` / `pushManual` /
/// `syncNow` with `extends WorkoutSyncService`, and extension methods dispatch
/// statically — moving those into an extension would mean the real
/// implementation ran while the fake sat unused. Keeping them as thin methods
/// on the class preserves every override; only the shared body moved here.
class WorkoutSyncSession {
  /// Creates a session bound to one repo and one pair of backends.
  const WorkoutSyncSession({
    required this.owner,
    required this.repo,
    required this.token,
    required this.pathPrefix,
    required this.logFilename,
    required this.encode,
    required this.decode,
    required this.openFirebaseClient,
    required this.openStateStore,
    required this.openLogStore,
    this.httpClient,
  });

  /// The repo owner/org to sync with.
  final String owner;

  /// The repo name to sync with.
  final String repo;

  /// The GitHub token. Empty when only Firebase is configured, which is what
  /// [SyncSettings] reports and what the mirror treats as unauthenticated.
  final String token;

  /// Directory prefix every device's log lives under.
  final String pathPrefix;

  /// Filename of a device's log within its directory.
  final String logFilename;

  /// Serializes a log for storage.
  final String Function(Log log) encode;

  /// Parses a stored log.
  final Log Function(String text) decode;

  /// Opens the Firebase backend, or returns null when not set up.
  final Future<FirebaseRestClient?> Function() openFirebaseClient;

  /// Opens the revision cache that lets an unchanged peer be skipped.
  final Future<SyncStateStore> Function() openStateStore;

  /// Opens this device's local log: the outbox a tick pushes from and the
  /// cache it keeps what it pulled in.
  final Future<LogStore> Function() openLogStore;

  /// Overrides the HTTP client; tests point this at a mock.
  final http.Client? httpClient;

  /// The tail of the tick queue, null while no tick runs. Ticks run one
  /// after another, never side by side: two overlapping ticks each push
  /// their own snapshot, and the one that lands last can drop a record the
  /// other just added.
  ///
  /// Null when idle rather than a completed future: a future is bound to the
  /// zone that made it, so a long-lived one would tie every later tick to a
  /// zone that may be gone (a finished widget test's, for one).
  static Future<void>? _tail;

  /// How long one tick may take before it is reported failed. Bounded
  /// because the queue waits on it: one half-open request would otherwise
  /// hold every later tick (and the retry) until the app restarts.
  @visibleForTesting
  static Duration tickTimeout = const Duration(minutes: 2);

  /// Forgets a tick a finished test left in flight; see `_tail`.
  @visibleForTesting
  static void resetQueueForTesting() => _tail = null;

  /// Runs one tick, merging [addition] into this device's log if given.
  ///
  /// [additions] merges many records in one round trip (the data import).
  /// Pass null for [addition] to round-trip the existing log unchanged — that
  /// is how a connectivity check gets a real answer without inventing a
  /// record to push.
  ///
  /// Never throws. [operation] names the caller in log lines; [successReason]
  /// and [failurePrefix] are passed in rather than derived, so the three
  /// callers keep the exact strings their tests assert on.
  Future<PushResult> run({
    required String operation,
    required String successReason,
    required String failurePrefix,
    Record? addition,
    Log? additions,
  }) {
    Future<PushResult> tick() =>
        _runNow(
          operation: operation,
          successReason: successReason,
          failurePrefix: failurePrefix,
          addition: addition,
          additions: additions,
        ).timeout(
          tickTimeout,
          onTimeout: () {
            final reason =
                '$failurePrefix: no answer within ${tickTimeout.inSeconds} s';
            log('WorkoutSyncService.$operation: $reason', level: 1000);
            return PushResult(pushed: false, reason: reason);
          },
        );
    final previous = _tail;
    final result = previous == null ? tick() : previous.then((_) => tick());
    final done = result.then<void>((_) {}, onError: (Object _) {});
    _tail = done;
    unawaited(
      done.then((_) {
        if (identical(_tail, done)) _tail = null;
      }),
    );
    return result;
  }

  Future<PushResult> _runNow({
    required String operation,
    required String successReason,
    required String failurePrefix,
    Record? addition,
    Log? additions,
  }) async {
    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: token,
      httpClient: httpClient,
    );
    final firebase = await openFirebaseClient();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      final path = '$pathPrefix/$currentSyncDeviceId/$logFilename';
      final existingText = await client.getFileText(path);
      final existingLog = existingText == null
          ? <String, Record>{}
          : decode(existingText);
      final incoming = <String, Record>{
        ...?additions,
        ?addition?.id: ?addition,
      };
      // The local log holds every record a failed or unconfigured push kept,
      // so this tick sends them too. The remote own file stays in the merge:
      // after a reinstall it is the only copy of this device's history.
      final local = await openLogStore();
      final localLog = mergeLogs(
        mergeLogs(existingLog, local.snapshot()),
        incoming,
      );
      final merged = await syncLog(
        client: client,
        deviceId: currentSyncDeviceId,
        legacyDeviceId: legacySyncDeviceId,
        pathPrefix: pathPrefix,
        localLog: localLog,
        encode: encode,
        decode: decode,
        // Without this every push re-uploads the whole log and every pull
        // re-downloads every peer's, regardless of change -- the traffic the
        // Firebase free tier's monthly budget depends on not happening.
        stateStore: await openStateStore(),
      );
      await _keepPulled(local, merged, operation);
      return PushResult(pushed: true, reason: successReason);
    } on Object catch (error, stackTrace) {
      // Deliberately broad: a GitHubSyncError was the only case handled
      // before, so a Firebase error, an auth failure or a dropped connection
      // vanished with no trace at all. Still swallowed rather than rethrown
      // -- a sync failure must not cost the user their finished workout --
      // but now it is reported, not hidden.
      final reason = '$failurePrefix: $error';
      log(
        'WorkoutSyncService.$operation failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return PushResult(pushed: false, reason: reason);
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Keeps [merged] in [local] for offline reads. Merged onto the store as
  /// it is NOW, not replaced: a workout written while this tick ran must
  /// survive it. Never throws: the tick already reached the remote, so a
  /// local write failure costs only the offline copy, and is logged.
  static Future<void> _keepPulled(
    LogStore local,
    Log merged,
    String operation,
  ) async {
    try {
      await local.replaceAll(mergeLogs(local.snapshot(), merged));
    } on Object catch (error, stackTrace) {
      log(
        'WorkoutSyncService.$operation synced, but the local copy was not '
        'saved; offline reads show the previous one',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
    }
  }
}
