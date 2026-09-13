/// Fakes `path_provider` so `AssetSource` playback works in widget tests.
///
/// `audioplayers` copies an asset into the temporary directory before it can
/// play it, so without this every break-end cue in a widget test dies with
/// `MissingPluginException` — swallowed by `_playBreakEndCue`'s catch, which
/// means the sound silently never played and no test could tell.
library;

import 'dart:io';

import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

class _FakePathProvider extends PathProviderPlatform {
  _FakePathProvider(this._root);

  final String _root;

  @override
  Future<String?> getTemporaryPath() async => _root;

  @override
  Future<String?> getApplicationSupportPath() async => _root;

  @override
  Future<String?> getApplicationDocumentsPath() async => _root;

  @override
  Future<String?> getApplicationCachePath() async => _root;

  @override
  Future<String?> getLibraryPath() async => _root;

  @override
  Future<String?> getDownloadsPath() async => _root;

  @override
  Future<String?> getExternalStoragePath() async => _root;

  @override
  Future<List<String>?> getExternalCachePaths() async => [_root];

  @override
  Future<List<String>?> getExternalStoragePaths({
    StorageDirectory? type,
  }) async => [_root];
}

/// Points every `path_provider` lookup at a throwaway directory.
///
/// Returns the directory so a test can inspect what was written there.
Directory installFakePathProvider() {
  final dir = Directory.systemTemp.createTempSync('workout_app_test_');
  PathProviderPlatform.instance = _FakePathProvider(dir.path);
  return dir;
}
