import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/backup_service.dart';

void main() {
  late Directory tempDir;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('backup_service_test_');
    BackupService.baseDirForTesting = tempDir.path;
  });

  tearDown(() {
    BackupService.baseDirForTesting = kBackupDir;
    tempDir.deleteSync(recursive: true);
  });

  test('baseDirForTesting getter reflects the last setter value', () {
    expect(BackupService.baseDirForTesting, tempDir.path);
  });

  test('export then readBackup round-trips the data', () async {
    await BackupService.instance.export({'a': 1, 'b': 'two'});
    final result = await BackupService.instance.readBackup();
    expect(result, {'a': 1, 'b': 'two'});
  });

  test('readBackup returns null when nothing was exported', () async {
    expect(await BackupService.instance.readBackup(), isNull);
  });

  test('readBackup returns null for unreadable JSON', () async {
    File('${tempDir.path}/backup.json').writeAsStringSync('not json');
    expect(await BackupService.instance.readBackup(), isNull);
  });

  test('exportSyncToken then readSyncToken round-trips the token', () async {
    await BackupService.instance.exportSyncToken('gho_abc123');
    expect(await BackupService.instance.readSyncToken(), 'gho_abc123');
  });

  test('readSyncToken returns null when nothing was exported', () async {
    expect(await BackupService.instance.readSyncToken(), isNull);
  });

  test('exportSyncToken with an empty token deletes an existing file', () async {
    await BackupService.instance.exportSyncToken('gho_abc123');
    await BackupService.instance.exportSyncToken('');
    expect(await BackupService.instance.readSyncToken(), isNull);
  });

  test('exportSyncToken with an empty token is a no-op when no file exists', () async {
    await BackupService.instance.exportSyncToken('');
    expect(await BackupService.instance.readSyncToken(), isNull);
  });

  test('export creates the target directory if missing', () async {
    final nested = Directory('${tempDir.path}/nested');
    BackupService.baseDirForTesting = nested.path;
    await BackupService.instance.export({'x': 1});
    expect(await BackupService.instance.readBackup(), {'x': 1});
  });

  test('exportSyncToken creates the target directory if missing', () async {
    final nested = Directory('${tempDir.path}/nested2');
    BackupService.baseDirForTesting = nested.path;
    await BackupService.instance.exportSyncToken('tok');
    expect(await BackupService.instance.readSyncToken(), 'tok');
  });

  test('export swallows errors when the path cannot be created', () async {
    // A regular file used as the "directory" makes Directory.createSync
    // throw -- export must swallow it, not crash the caller.
    final blocker = File('${tempDir.path}/blocker');
    blocker.writeAsStringSync('x');
    BackupService.baseDirForTesting = blocker.path;
    await BackupService.instance.export({'x': 1});
    // No exception reaching here is the assertion.
  });

  test(
    'exportSyncToken swallows errors when the path cannot be created',
    () async {
      final blocker = File('${tempDir.path}/blocker2');
      blocker.writeAsStringSync('x');
      BackupService.baseDirForTesting = blocker.path;
      await BackupService.instance.exportSyncToken('tok');
    },
  );

  test('readBackup swallows filesystem errors', () async {
    // Points at a directory instead of a file so File.readAsString throws.
    final asDir = Directory('${tempDir.path}/backup.json');
    asDir.createSync();
    expect(await BackupService.instance.readBackup(), isNull);
  });

  test('readSyncToken swallows filesystem errors', () async {
    final asDir = Directory('${tempDir.path}/sync_token');
    asDir.createSync();
    expect(await BackupService.instance.readSyncToken(), isNull);
  });
}
