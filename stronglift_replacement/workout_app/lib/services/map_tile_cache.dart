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

Future<TileProvider>? _opened;

/// The shared disk-cached OSM provider; opened once per process.
///
/// If the cache directory cannot be had, the map still works over the
/// network without a cache, and the reason is logged at warning level.
Future<TileProvider> openOsmTileProvider() => _opened ??= _open();

/// Forgets the opened provider (tests only).
@visibleForTesting
void resetOsmTileProvider() => _opened = null;

Future<TileProvider> _open() async {
  try {
    final dir = await getApplicationCacheDirectory();
    return buildCachedTileProvider('${dir.path}/osm_tiles');
  } on Object catch (error) {
    logMapWarning('map tile cache unavailable, tiles will not persist: $error');
    return NetworkTileProvider();
  }
}

/// Logs [message] at warning level (900), loud in `flutter logs` too.
void logMapWarning(String message) {
  developer.log(message, name: 'RunMap', level: 900);
  debugPrint('RunMap WARNING: $message');
}
