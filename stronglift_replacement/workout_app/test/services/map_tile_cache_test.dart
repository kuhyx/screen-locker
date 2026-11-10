import 'dart:io';

import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_cache/flutter_map_cache.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:workout_app/services/map_tile_cache.dart';

import '../fake_path_provider.dart';
import '../widgets/_run_map_fixtures.dart';

/// A platform with no cache directory (getApplicationCacheDirectory throws).
class _NoCacheDir extends PathProviderPlatform {
  @override
  Future<String?> getApplicationCachePath() async => null;
}

void main() {
  setUp(resetOsmTileProvider);

  test('the OSM source and policy constants', () {
    expect(osmTileUrl, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    expect(osmUserAgentPackage, 'com.kuhy.workout_app');
    expect(tileMaxStale, const Duration(days: 365));
  });

  test('buildCachedTileProvider caches on disk under the given dir', () {
    final dir = Directory.systemTemp.createTempSync('tile_cache_test_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final provider = buildCachedTileProvider('${dir.path}/osm_tiles');
    expect(provider, isA<CachedTileProvider>());
    expect(provider.supportsCancelLoading, isTrue);
  });

  test('every open is a fresh cached provider (TileLayer disposes it)', () async {
    final dir = installFakePathProvider();
    addTearDown(() => dir.deleteSync(recursive: true));
    final first = await openOsmTileProvider();
    final second = await openOsmTileProvider();
    expect(first, isA<CachedTileProvider>());
    expect(second, isA<CachedTileProvider>());
    expect(identical(second, first), isFalse);
  });

  test('without a cache dir: network provider and a warning', () async {
    PathProviderPlatform.instance = _NoCacheDir();
    late TileProvider provider;
    final lines = await capturingDebugPrint(() async {
      provider = await openOsmTileProvider();
    });
    expect(provider, isA<NetworkTileProvider>());
    // Looked up once: the second map falls back without a second warning.
    expect(await openOsmTileProvider(), isA<NetworkTileProvider>());
    expect(
      lines.where((l) => l.contains('WARNING') && l.contains('persist')),
      hasLength(1),
    );
  });
}
