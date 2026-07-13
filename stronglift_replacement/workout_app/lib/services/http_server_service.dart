/// Tiny HTTP server that exposes the latest workout JSON on the local network.
///
/// Purpose: allows the PC to verify the workout even when USB-debugging /
/// ADB is not available. The PC scans for port [kWorkoutServerPort] on the
/// local subnet and GETs /workout.
///
/// Security note: this only serves workout data and only on the local
/// network. No authentication is needed for a home-network use case.
library;

import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/services/sync_service.dart';

/// Port the HTTP server listens on. Must match the constant on the PC side.
const int kWorkoutServerPort = 8765;

/// Singleton HTTP server that serves the latest workout JSON over LAN.
class HttpServerService {
  HttpServerService._();

  /// Singleton instance.
  static final HttpServerService instance = HttpServerService._();

  HttpServer? _server;

  /// The most recent workout JSON string (updated after each finished workout).
  String? _latestJson;

  /// Returns all non-loopback IPv4 addresses the server is reachable on.
  Future<List<String>> get localAddresses async {
    final addrs = <String>[];
    for (final iface in await NetworkInterface.list()) {
      for (final addr in iface.addresses) {
        if (addr.type == InternetAddressType.IPv4 && !addr.isLoopback) {
          addrs.add(addr.address);
        }
      }
    }
    return addrs;
  }

  /// The most recent workout JSON served at /workout, or null if none.
  String? get latestWorkout => _latestJson;

  /// Updates the JSON payload served at /workout.
  set latestWorkout(String json) => _latestJson = json;

  /// Starts the HTTP server, loading the last saved workout from disk first.
  Future<void> start() async {
    if (_server != null) return; // already running
    await _loadFromDisk();
    try {
      _server = await HttpServer.bind(
        InternetAddress.anyIPv4,
        kWorkoutServerPort,
      );
      unawaited(_serve());
    } on SocketException {
      // Port already in use or binding failed — not fatal.
      _server = null;
    }
  }

  /// On startup, try to load the last saved workout JSON from disk so the
  /// HTTP endpoint is populated even before the next workout is completed.
  Future<void> _loadFromDisk() async {
    final candidates = <String>[kSyncFilePath];
    // External storage is Android-only; getExternalStorageDirectory() throws an
    // UnsupportedError (not an Exception) on other platforms (desktop / test
    // host), so guard the call rather than trying to catch it.
    // coverage:ignore-start
    // Android-only: getExternalStorageDirectory is unavailable on the Linux
    // test host, so this block can't be exercised in CI.
    if (Platform.isAndroid) {
      try {
        final dir = await getExternalStorageDirectory();
        if (dir != null) candidates.add('${dir.path}/workout_result.json');
      } on Exception {
        // Ignore; the /sdcard path is tried first.
      }
      // coverage:ignore-end
    }
    for (final path in candidates) {
      final file = File(path);
      // coverage:ignore-start
      // Only reachable when a candidate file exists — i.e. on a real device
      // with /sdcard (or Android external storage). Not present on the host.
      if (file.existsSync()) {
        try {
          _latestJson = await file.readAsString();
          return;
        } on IOException {
          // Try next path.
        }
      }
      // coverage:ignore-end
    }
  }

  /// Clears the cached workout JSON (test seam so the "no data yet" HTTP
  /// response can be exercised after other tests have set it).
  @visibleForTesting
  void resetForTesting() => _latestJson = null;

  Future<void> _serve() async {
    final server = _server;
    if (server == null) return;
    await for (final req in server) {
      if (req.method == 'GET' && req.uri.path == '/workout') {
        if (_latestJson != null) {
          req.response
            ..statusCode = HttpStatus.ok
            ..headers.contentType = ContentType.json
            ..write(_latestJson);
        } else {
          req.response.statusCode = HttpStatus.notFound;
          req.response.write('{"error":"no workout data yet"}');
        }
      } else {
        req.response.statusCode = HttpStatus.notFound;
        req.response.write('{"error":"not found"}');
      }
      await req.response.close();
    }
  }

  /// Stops the HTTP server.
  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }
}
