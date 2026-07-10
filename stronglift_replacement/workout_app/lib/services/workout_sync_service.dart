/// Pushes completed workout sessions to the shared GitHub sync repo.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
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
}
