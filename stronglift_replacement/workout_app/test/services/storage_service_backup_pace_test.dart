// The pace target rides in the /sdcard backup and comes back on a restore.
@TestOn('vm')
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:shared_preferences_platform_interface/types.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/pace_target_store.dart';
import 'package:workout_app/services/storage_service.dart';

import '../widgets/_run_map_fixtures.dart' show capturingDebugPrint;
import 'storage_service_runs_fixtures.dart';

/// A preferences platform that can be neither read nor written.
base class _BrokenPrefs extends InMemorySharedPreferencesAsync {
  _BrokenPrefs() : super.empty();

  @override
  Future<int?> getInt(String key, SharedPreferencesOptions options) =>
      throw StateError('prefs unavailable');

  @override
  Future<bool> setInt(
    String key,
    int value,
    SharedPreferencesOptions options,
  ) => throw StateError('prefs unavailable');
}

void _freshPrefs() => SharedPreferencesAsyncPlatform.instance =
    InMemorySharedPreferencesAsync.empty();

/// Writes a backup (a write triggers one) and returns it once it is on disk.
Future<Map<String, dynamic>> _backup() async {
  await svc.setLastWorkoutType('A');
  for (var i = 0; i < 150; i++) {
    final backup = await BackupService.instance.readBackup();
    if (backup != null && (backup['settings'] as List).isNotEmpty) {
      return backup;
    }
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
  fail('backup.json never written');
}

/// A reinstall: new DB, preferences holding [stale] (null: nothing), restore.
Future<void> _reinstall({int? stale}) async {
  await freshInstall();
  _freshPrefs();
  if (stale != null) await PrefsPaceTargetStore().save(stale);
  await svc.restoreFromBackupIfNeeded();
}

void main() {
  useRunsTransferSandbox();
  setUp(_freshPrefs);

  test('a set target round-trips through backup and restore', () async {
    await PrefsPaceTargetStore().save(295);
    expect((await _backup())['pace_target'], 295);

    await _reinstall(stale: 400);

    expect(await PrefsPaceTargetStore().stored(), 295);
  });

  test('"off" round-trips and replaces a stale target', () async {
    final backup = await _backup();
    expect(backup.containsKey('pace_target'), isTrue);
    expect(backup['pace_target'], isNull);

    await _reinstall(stale: 400);

    expect(await PrefsPaceTargetStore().stored(), isNull);
    expect(await PrefsPaceTargetStore().load(), kDefaultPaceTarget);
  });

  test('an older backup without the field restores as off', () async {
    await BackupService.instance.export({
      'exercise_state': <Object>[],
      'workout_history': <Object>[],
      'settings': <Object>[],
    });

    await _reinstall(stale: 400);

    expect(await PrefsPaceTargetStore().stored(), isNull);
  });

  test('a target that is not a number restores as off, loudly', () async {
    await BackupService.instance.export({'pace_target': 'fast'});
    final lines = await capturingDebugPrint(() => _reinstall(stale: 400));
    expect(await PrefsPaceTargetStore().stored(), isNull);
    expect(lines.where((l) => l.contains('not a number')), hasLength(1));
  });

  test('an out-of-range target is clamped on restore', () async {
    await BackupService.instance.export({'pace_target': 60});
    await _reinstall();
    expect(await PrefsPaceTargetStore().stored(), kMinPaceTarget);
  });

  test('unreadable preferences leave the field out and say so', () async {
    SharedPreferencesAsyncPlatform.instance = _BrokenPrefs();
    late Map<String, dynamic> backup;
    final lines = await capturingDebugPrint(
      () async => backup = await _backup(),
    );
    expect(backup.containsKey('pace_target'), isFalse);
    expect(lines.where((l) => l.contains('NOT in this backup')), hasLength(1));
  });

  test('unwritable preferences do not stop the rest of the restore', () async {
    await BackupService.instance.export({
      'settings': [
        {'key': 'last_workout_type', 'value': 'B', 'updated_at': 1},
      ],
      'pace_target': 295,
    });
    await freshInstall();
    SharedPreferencesAsyncPlatform.instance = _BrokenPrefs();
    final lines = await capturingDebugPrint(svc.restoreFromBackupIfNeeded);
    expect(await svc.getNextWorkoutType(), 'A'); // last was B: restored
    expect(lines.where((l) => l.contains('NOT restored')), hasLength(1));
  });
}
