import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_upload_credentials.dart';

import '../fake_secure_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('provisioning', () {
    late Directory dir;
    setUp(() {
      installFakeSecureStorage();
      dir = Directory.systemTemp.createTempSync('provision_test_');
      addTearDown(() => dir.deleteSync(recursive: true));
    });

    RunCredentialStore store() =>
        RunCredentialStore(externalDir: () async => dir);
    File file() => File('${dir.path}/$kProvisionFileName');

    test('a login file is imported into secure storage and deleted', () async {
      file().writeAsStringSync(
        jsonEncode({
          'url': 'https://cloud.example/',
          'user': 'workout_app',
          'password': 'secret',
        }),
      );
      final s = store();
      expect(await s.read(), isNull);

      final outcome = await s.importProvisionFile();

      expect(outcome.status, ProvisionStatus.imported);
      expect(file().existsSync(), isFalse);
      final login = (await s.read())!;
      expect(login.url, 'https://cloud.example');
      expect(login.user, 'workout_app');
      expect(login.password, 'secret');
      expect(
        login.authorization,
        'Basic ${base64.encode(utf8.encode('workout_app:secret'))}',
      );
    });

    test('no file, or no directory, is a quiet no-op', () async {
      expect(
        (await store().importProvisionFile()).status,
        ProvisionStatus.absent,
      );
      final none = RunCredentialStore(externalDir: () async => null);
      expect((await none.importProvisionFile()).status, ProvisionStatus.absent);
      // The default directory lookup answers null off Android.
      expect(
        (await RunCredentialStore().importProvisionFile()).status,
        ProvisionStatus.absent,
      );
    });

    test('an unusable file is kept and reported', () async {
      final bad = <String>[
        'not json',
        '[]',
        jsonEncode({'url': 'https://x', 'user': 'u'}),
        jsonEncode({'url': 'ftp://x', 'user': 'u', 'password': 'p'}),
        jsonEncode({'url': 'nonsense', 'user': 'u', 'password': 'p'}),
        jsonEncode({'url': 'https://x', 'user': '', 'password': 'p'}),
        jsonEncode({'url': 'https://x', 'user': 'u', 'password': ''}),
      ];
      for (final text in bad) {
        file().writeAsStringSync(text);
        final s = store();
        final outcome = await s.importProvisionFile();
        expect(outcome.status, ProvisionStatus.invalid, reason: text);
        expect(outcome.reason, contains('provision_run_upload.sh'));
        expect(file().existsSync(), isTrue);
        expect(await s.read(), isNull);
      }
    });
  });
}
