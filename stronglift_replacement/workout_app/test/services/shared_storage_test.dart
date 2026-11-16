import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/runnerup_import_state.dart';
import 'package:workout_app/services/shared_storage.dart';
import 'package:workout_app/services/sync_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  void answer(Object? Function(MethodCall call)? handler) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          Sandbox.channel,
          handler == null ? null : (call) async => handler(call),
        );
  }

  tearDown(() {
    answer(null);
    Sandbox.enabled = false;
    Sandbox.packageName = kDailyPackage;
  });

  test('the daily build keeps the paths the PC reads', () {
    expect(sharedPathFor(kDailyPackage, kBackupDir), '/sdcard/WorkoutTracker');
    expect(
      sharedPathFor(kDailyPackage, kSyncFilePath),
      '/sdcard/workout_result.json',
    );
  });

  test('any other package gets its own sibling path', () {
    expect(
      sharedPathFor('com.kuhy.slot3', kBackupDir),
      '/sdcard/WorkoutTracker.com.kuhy.slot3',
    );
    expect(
      sharedPathFor('com.kuhy.slot3', kSyncFilePath),
      isNot(kSyncFilePath),
    );
    expect(
      sharedPathFor('com.kuhy.slot3', kRunnerUpLocalDir),
      isNot(kRunnerUpLocalDir),
    );
  });

  test('init asks MainActivity for the package name', () async {
    answer((call) => call.method == 'packageName' ? 'com.kuhy.slot3' : false);
    await Sandbox.init();
    expect(Sandbox.packageName, 'com.kuhy.slot3');
  });

  test('an older MainActivity without packageName means the daily build',
      () async {
    answer((call) {
      if (call.method == 'packageName') {
        throw MissingPluginException();
      }
      return false;
    });
    await Sandbox.init();
    expect(Sandbox.packageName, kDailyPackage);
  });

  test('no channel at all means the daily build', () async {
    answer(null);
    await Sandbox.init({});
    expect(Sandbox.packageName, kDailyPackage);
  });

  test('applySharedStoragePaths moves a slot off the daily files', () {
    final savedBase = BackupService.baseDir;
    final savedSync = SyncService.filePath;
    addTearDown(() {
      BackupService.baseDir = savedBase;
      SyncService.filePath = savedSync;
    });
    applySharedStoragePaths('com.kuhy.slot3');
    expect(BackupService.baseDir, '/sdcard/WorkoutTracker.com.kuhy.slot3');
    expect(SyncService.filePath, '/sdcard/workout_result.json.com.kuhy.slot3');

    applySharedStoragePaths(kDailyPackage);
    expect(BackupService.baseDir, kBackupDir);
    expect(SyncService.filePath, kSyncFilePath);
  });
}
