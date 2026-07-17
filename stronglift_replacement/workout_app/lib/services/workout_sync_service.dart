/// Pushes completed workout sessions to the shared GitHub sync repo.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/sync_settings.dart';

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
    // Dart forbids private named params, so this can't be an initializing
    // formal; assign it explicitly (mirrors crdt_sync_dart's GitHubClient).
    // ignore: prefer_initializing_formals
  }) : _httpClient = httpClient;

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
    if (!settings.isConfigured) return;

    final client = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
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
      );
    } on GitHubSyncError catch (error) {
      debugPrint('WorkoutSyncService.push failed: $error');
    } finally {
      client.close();
    }
  }

  /// Pushes a pre-built manual-workout [record] to `devices/phone/log.json`,
  /// merging with whatever this device has already pushed. Same swallow-on-
  /// failure contract as [push].
  Future<void> pushManual(Record record) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured) return;

    final client = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
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
      );
    } on GitHubSyncError catch (error) {
      debugPrint('WorkoutSyncService.pushManual failed: $error');
    } finally {
      client.close();
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
    if (!settings.isConfigured) {
      debugPrint(
        'WorkoutSyncService: NOT reading synced workouts — no sync token/repo '
        'configured in Settings, so this phone cannot see the PC history.',
      );
      return const [];
    }

    final client = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
    try {
      final merged = <String, Record>{};
      for (final device in await client.listDirectory(_pathPrefix)) {
        final text = await client.getFileText('$_pathPrefix/$device/$_logFilename');
        if (text == null) continue;
        _mergeRecords(_decode(text), merged, kind: kind);
      }
      return merged.values
          .map((r) => (r.fields['payload']!.$1! as Map).cast<String, dynamic>())
          .toList();
    } on GitHubSyncError catch (error) {
      final which = kind ?? 'any';
      debugPrint(
        'WorkoutSyncService: FAILED reading synced workouts '
        '(kind=$which) from $owner/$repo: $error — history may be incomplete.',
      );
      return const [];
    } finally {
      client.close();
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
