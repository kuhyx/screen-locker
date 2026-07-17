import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/sync_settings.dart';

import '../fake_secure_storage.dart';

void main() {
  // installFakeSecureStorage touches the test binary messenger, which needs
  // the binding up first (widget tests get this for free via testWidgets).
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('sync_settings_test_');
    BackupService.baseDirForTesting = tempDir.path;
  });

  tearDown(() {
    BackupService.baseDirForTesting = kBackupDir;
    tempDir.deleteSync(recursive: true);
  });

  test('load returns an empty token on a fresh install', () async {
    installFakeSecureStorage();
    final s = await SyncSettings.load();
    expect(s.token, '');
    expect(s.isConfigured, isFalse);
  });

  test('load reads a previously saved token from the keystore', () async {
    installFakeSecureStorage(initial: {'sync.token': 'fromKeystore'});
    final s = await SyncSettings.load();
    expect(s.token, 'fromKeystore');
    expect(s.isConfigured, isTrue);
  });

  test('save persists the token to the keystore', () async {
    installFakeSecureStorage();
    final ok = await const SyncSettings(token: 'tok').save();
    expect(ok, isTrue);

    final s = await SyncSettings.load();
    expect(s.token, 'tok');
  });

  test('save with an empty token deletes any existing entry', () async {
    installFakeSecureStorage(initial: {'sync.token': 'stale'});
    final ok = await const SyncSettings(token: '').save();
    expect(ok, isTrue);

    final s = await SyncSettings.load();
    expect(s.token, '');
  });

  test('load returns an empty token when the keystore is unavailable', () async {
    installFakeSecureStorage(throwing: true);
    final s = await SyncSettings.load();
    expect(s.token, '');
  });

  test('save returns false when the keystore is unavailable', () async {
    installFakeSecureStorage(throwing: true);
    final ok = await const SyncSettings(token: 'tok').save();
    expect(ok, isFalse);
  });

  test('defaultClientId is baked in for the Connect GitHub button', () {
    expect(SyncSettings.defaultClientId, isNotEmpty);
  });

  test('save mirrors the token to the external-storage backup', () async {
    installFakeSecureStorage();
    await const SyncSettings(token: 'gho_backed_up').save();
    expect(
      await BackupService.instance.readSyncToken(),
      'gho_backed_up',
    );
  });

  test(
    'save with an empty token clears the external-storage backup too',
    () async {
      installFakeSecureStorage();
      await const SyncSettings(token: 'gho_x').save();
      await const SyncSettings(token: '').save();
      expect(await BackupService.instance.readSyncToken(), isNull);
    },
  );

  test(
    'load recovers the token from the backup when the keystore is empty '
    '(e.g. right after a reinstall) and re-seeds the keystore',
    () async {
      installFakeSecureStorage();
      await BackupService.instance.exportSyncToken('gho_recovered');

      final s = await SyncSettings.load();
      expect(s.token, 'gho_recovered');

      // Re-seeded so the next load doesn't need the backup fallback.
      final again = await SyncSettings.load();
      expect(again.token, 'gho_recovered');
    },
  );

  test(
    'load recovers from the backup even when the keystore write fails',
    () async {
      installFakeSecureStorage(throwing: true);
      await BackupService.instance.exportSyncToken('gho_recovered2');

      final s = await SyncSettings.load();
      expect(s.token, 'gho_recovered2');
    },
  );

  group('recoverFromBackup', () {
    test('re-seeds the keystore when the backup holds a different token', () async {
      // A stale keystore entry shadows a good backup forever: load() only
      // consults the backup when the keystore is EMPTY.
      installFakeSecureStorage(initial: {'sync.token': 'stale'});
      await const SyncSettings(token: 'good-from-backup').save();
      // Put the stale token back in the keystore (save() overwrote it).
      installFakeSecureStorage(initial: {'sync.token': 'stale'});

      final recovered = await SyncSettings.recoverFromBackup('stale');

      expect(recovered, 'good-from-backup');
      // The keystore was re-seeded, so the next load() returns the good one.
      expect((await SyncSettings.load()).token, 'good-from-backup');
    });

    test('returns null when the backup holds the same rejected token', () async {
      installFakeSecureStorage(initial: {'sync.token': 'same'});
      await const SyncSettings(token: 'same').save();
      expect(await SyncSettings.recoverFromBackup('same'), isNull);
    });

    test('returns null when there is no backup to recover from', () async {
      installFakeSecureStorage(initial: {'sync.token': 'rejected'});
      expect(await SyncSettings.recoverFromBackup('rejected'), isNull);
    });

    test('still returns the token when the keystore write fails', () async {
      installFakeSecureStorage();
      await const SyncSettings(token: 'good-from-backup').save();
      installFakeSecureStorage(throwing: true);
      expect(await SyncSettings.recoverFromBackup('stale'), 'good-from-backup');
    });
  });
}
