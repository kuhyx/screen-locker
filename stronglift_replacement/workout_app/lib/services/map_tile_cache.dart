/// The OSM tile source and its on-disk cache.
///
/// Tiles come from tile.openstreetmap.org and are kept in the app's cache
/// directory (flutter_map_cache over dio_cache_interceptor) with a one-year
/// max-stale, so an area visited once draws offline later. OSM's tile usage
/// policy needs a real User-Agent: the [TileLayer] sends
/// [osmUserAgentPackage].
library;

import 'dart:async';
import 'dart:developer' as developer;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_cache/flutter_map_cache.dart';
import 'package:http_cache_file_store/http_cache_file_store.dart';
import 'package:path_provider/path_provider.dart';

/// The OSM raster tile template.
const osmTileUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/// Sent as the tile User-Agent, as OSM's tile policy asks.
const osmUserAgentPackage = 'com.kuhy.workout_app';

/// How long a cached tile may be served when the network cannot refresh it.
const tileMaxStale = Duration(days: 365);

/// Opens a [TileProvider]; swapped for a fake in tests.
typedef TileProviderOpener = Future<TileProvider> Function();

/// A provider that caches into [cacheDir] (and serves stale tiles offline).
TileProvider buildCachedTileProvider(String cacheDir, {Dio? dio}) =>
    CachedTileProvider(
      store: FileCacheStore(cacheDir),
      maxStale: tileMaxStale,
      dio: dio,
    );

Future<String?>? _cacheDir;

/// A disk-cached OSM provider; each map gets its own.
///
/// Only the cache directory is looked up once per process. A provider is
/// never shared: `TileLayer` disposes its provider when the map goes away
/// (a `NetworkTileProvider` closes its HTTP client then), so a shared one
/// would be dead for the second map.
///
/// If the cache directory cannot be had, the map still works over the
/// network without a cache, and the reason is logged once at warning level.
Future<TileProvider> openOsmTileProvider() async {
  final dir = await (_cacheDir ??= _resolveCacheDir());
  return dir == null ? NetworkTileProvider() : buildCachedTileProvider(dir);
}

/// Forgets the looked-up cache directory (tests only).
@visibleForTesting
void resetOsmTileProvider() => _cacheDir = null;

Future<String?> _resolveCacheDir() async {
  try {
    final dir = await getApplicationCacheDirectory();
    return '${dir.path}/osm_tiles';
  } on Object catch (error) {
    final message = 'map tile cache unavailable, tiles not persisted: $error';
    developer.log(message, name: 'RunMap', level: 900);
    debugPrint('RunMap WARNING: $message');
    return null;
  }
}

/// Logs [message] at warning level (900), loud in `flutter logs` too.
void logMapWarning(String message) {
  developer.log(message, name: 'RunMap', level: 900);
  debugPrint('RunMap WARNING: $message');
}
