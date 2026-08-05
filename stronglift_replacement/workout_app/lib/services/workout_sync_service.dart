/// Pushes completed workout sessions to the shared GitHub sync repo.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/firebase_backend.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/services/sync_state_factory.dart';

const _deviceId = 'phone';
const _pathPrefix = 'screen-locker-sync/devices';
const _logFilename = 'log.json';

String _encode(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

/// Mirrors the PC-side `_workout_sync.py`: GitHub is used purely as dumb
/// file storage via the Contents API, one [Record] per completed session,
/// merged onto whatever this phone has already pushed. A missing token or a
/// failed push is swallowed here -- sync being unconfigured or unreachable
/// must never crash or delay the workout-completion flow that calls [push].
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

  /// Pushes [session] to `devices/phone/log.json`, merging with whatever
  /// this device has already pushed. No-ops silently if sync isn't
  /// configured; logs (but does not rethrow) any [GitHubSyncError].
  Future<void> push(WorkoutSession session) async {
    final settings = await SyncSettings.load();
    // Either backend counts. Gating on the GitHub token alone silently
    // dropped every push from a device connected only to Firebase -- and
    // once the mirror is retired that would be every device.
    if (!settings.isConfigured && !await _hasFirebaseAccount()) return;

    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
    final firebase = await _openFirebase();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      const path = '$_pathPrefix/$_deviceId/$_logFilename';
      final existingText = await client.getFileText(path);
      final existingLog = existingText == null
          ? <String, Record>{}
          : _decode(existingText);
      final record = Record(
        id: session.startTime.toIso8601String(),
        fields: {'payload': (session.toJson(), Hlc.newTick(_deviceId))},
      );
      final localLog = mergeLogs(existingLog, {record.id: record});
      await syncLog(
        client: client,
        deviceId: _deviceId,
        pathPrefix: _pathPrefix,
        localLog: localLog,
        encode: _encode,
        decode: _decode,
        // Without this every push re-uploads the whole log and every pull
        // re-downloads every peer's, regardless of change -- the traffic the
        // Firebase free tier's monthly budget depends on not happening.
        stateStore: await _openStateStore(),
      );
    } on GitHubSyncError catch (error) {
      debugPrint('WorkoutSyncService.push failed: $error');
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Pushes a pre-built manual-workout [record] to `devices/phone/log.json`,
  /// merging with whatever this device has already pushed. Same swallow-on-
  /// failure contract as [push].
  Future<void> pushManual(Record record) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) return;

    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
    final firebase = await _openFirebase();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      const path = '$_pathPrefix/$_deviceId/$_logFilename';
      final existingText = await client.getFileText(path);
      final existingLog = existingText == null
          ? <String, Record>{}
          : _decode(existingText);
      final localLog = mergeLogs(existingLog, {record.id: record});
      await syncLog(
        client: client,
        deviceId: _deviceId,
        pathPrefix: _pathPrefix,
        localLog: localLog,
        encode: _encode,
        decode: _decode,
        // Without this every push re-uploads the whole log and every pull
        // re-downloads every peer's, regardless of change -- the traffic the
        // Firebase free tier's monthly budget depends on not happening.
        stateStore: await _openStateStore(),
      );
    } on GitHubSyncError catch (error) {
      debugPrint('WorkoutSyncService.pushManual failed: $error');
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Returns every device's manual-workout payloads, merged and deduped by id
  /// (highest HLC wins), for computing the shared budget. Pull-only — unlike
  /// [pushManual] it never writes, so showing the budget can't mutate the repo.
  /// Returns an empty list if sync isn't configured or the repo is unreachable.
  Future<List<Map<String, dynamic>>> readMergedManualPayloads() =>
      _readMergedPayloads(kind: kManualWorkoutSyncKind);

  /// Every synced workout, whatever kind — manual, StrongLifts or RunnerUp.
  ///
  /// The PC publishes its whole `workout_log.json` (including verified runs),
  /// so this is what the history view needs to show the SAME workouts both
  /// devices know about. Deliberately unfiltered: the manual-workout budget
  /// uses [readMergedManualPayloads] instead.
  Future<List<Map<String, dynamic>>> readMergedWorkoutPayloads() =>
      _readMergedPayloads();

  Future<List<Map<String, dynamic>>> _readMergedPayloads({String? kind}) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      debugPrint(
        'WorkoutSyncService: NOT reading synced workouts — no sync backend '
        'configured in Settings, so this phone cannot see the PC history.',
      );
      return const [];
    }

    try {
      return await _fetchPayloads(settings.token, kind);
    } on GitHubSyncError catch (error) {
      var failure = error;
      // A stale keystore token shadows a good backup (SyncSettings.load only
      // falls back when the keystore is EMPTY), so retry once from the backup
      // rather than leaving history silently incomplete.
      final recovered = await SyncSettings.recoverFromBackup(settings.token);
      if (recovered != null) {
        try {
          final payloads = await _fetchPayloads(recovered, kind);
          debugPrint(
            'WorkoutSyncService: recovered the sync token from backup after '
            'the stored one was rejected ($failure).',
          );
          return payloads;
        } on GitHubSyncError catch (retryError) {
          failure = retryError;
        }
      }
      final which = kind ?? 'any';
      debugPrint(
        'WorkoutSyncService: FAILED reading synced workouts '
        '(kind=$which) from $owner/$repo: $failure — history may be incomplete.',
      );
      return const [];
    }
  }

  Future<List<Map<String, dynamic>>> _fetchPayloads(
    String token,
    String? kind,
  ) async {
    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: token,
      httpClient: _httpClient,
    );
    // Read-only: MirrorStore reads the union of both, so a workout logged
    // against either backend still shows up during the cutover.
    final firebase = await _openFirebase();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      final merged = <String, Record>{};
      for (final device in await client.listDirectory(_pathPrefix)) {
        final text = await client.getFileText(
          '$_pathPrefix/$device/$_logFilename',
        );
        if (text == null) continue;
        _mergeRecords(_decode(text), merged, kind: kind);
      }
      return merged.values
          .map((r) => (r.fields['payload']!.$1! as Map).cast<String, dynamic>())
          .toList();
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Merges records into [into], keeping the highest-HLC copy of each id.
  ///
  /// [kind] filters on the payload's `kind` discriminator; pass null to keep
  /// every workout kind. The manual-workout budget must only ever see manual
  /// self-reports (a verified run must not consume that budget), while the
  /// history view wants everything — hence the filter rather than two merges.
  static void _mergeRecords(Log log, Map<String, Record> into, {String? kind}) {
    for (final entry in log.entries) {
      final field = entry.value.fields['payload'];
      if (field == null) continue;
      final payload = field.$1;
      if (payload is! Map) continue;
      if (kind != null && payload['kind'] != kind) continue;
      final existing = into[entry.key];
      if (existing == null || existing.fields['payload']!.$2 < field.$2) {
        into[entry.key] = entry.value;
      }
    }
  }
}
