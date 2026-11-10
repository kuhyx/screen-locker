/// Network refusal for the sandbox flavor.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:workout_app/services/pc_poke_wire.dart';

/// Makes every `dart:io` HTTP connection fail before a socket is opened --
/// except the workout poke to the configured PC and OSM map tiles.
///
/// Installed as `HttpOverrides.global` by `main` in the sandbox. Firebase and
/// GitHub sync both go through `package:http`, whose IO client is built from
/// `HttpClient()` and therefore from these overrides — one seam, not one
/// guard per service. A refused connection surfaces as a normal sync failure
/// in the UI, which is the honest answer: the sandbox is offline by design.
///
/// The single exception is `http://<pokeHost>:8774/v1/workout`, so a sandbox
/// workout can time the PC round trip. The PC verifies the signed
/// `"sandbox": true` and never writes or credits it. Firebase and GitHub are
/// https on 443 and can never match.
///
/// The other exception is `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
/// (zoom 0-19) for the run map, under OSM's tile usage policy: the map sends
/// a real User-Agent, caches tiles on disk, never prefetches, and nothing else
/// in the app GETs that host.
class SandboxHttpOverrides extends HttpOverrides {
  /// The PC host the poke may reach; set by `PcPairing` whenever the host is
  /// loaded or saved. Null means no exception at all.
  static String? pokeHost;

  /// Whether [uri] is exactly the poke endpoint on the configured PC.
  static bool allows(Uri uri) =>
      pokeHost != null &&
      uri.scheme == 'http' &&
      uri.host == pokeHost &&
      uri.port == kPcPokePort &&
      uri.path == kPcPokePath;

  /// The only tile host the sandbox may reach.
  static const tileHost = 'tile.openstreetmap.org';

  static final _tilePath = RegExp(r'^/(\d|1[0-9])/\d+/\d+\.png$');

  /// Whether [uri] is an OSM raster tile (https, port 443, zoom <= 19).
  static bool allowsTile(Uri uri) =>
      uri.scheme == 'https' &&
      uri.host == tileHost &&
      uri.port == 443 &&
      !uri.hasQuery &&
      _tilePath.hasMatch(uri.path);

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..connectionFactory = (uri, proxyHost, proxyPort) {
        if (proxyHost == null && allows(uri)) {
          debugPrint(
            'WorkoutSandbox: allowing the PC poke to ${uri.host}:${uri.port}',
          );
          return Socket.startConnect(uri.host, uri.port);
        }
        if (proxyHost == null && allowsTile(uri)) {
          debugPrint('WorkoutSandbox: allowing OSM tile ${uri.path}');
          return Socket.startConnect(uri.host, uri.port);
        }
        debugPrint(
          'WorkoutSandbox: refused network connection to ${uri.host} — the '
          'sandbox never talks to Firebase or GitHub.',
        );
        throw const SocketException(
          'sandbox flavor: network disabled by design',
        );
      };
  }
}
