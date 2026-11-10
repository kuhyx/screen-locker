@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/runnerup_dav.dart';
import 'package:workout_app/services/runnerup_importer.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_secure_storage.dart';
import '_runnerup_fake_dufs.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('the phone folder scan', () {
    late Directory dir;
    late FakeDufs dufs;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      StorageService.resetForTesting();
      await StorageService.init();
      dufs = FakeDufs(fixtureTcx());
      dir = Directory.systemTemp.createTempSync('runnerup_local');
      addTearDown(() => dir.deleteSync(recursive: true));
    });

    RunnerUpImporter importer({bool canRead = true}) => RunnerUpImporter(
      client: dufs.client,
      loadLogin: fakeLogin,
      canReadStorage: () async => canRead,
      localDir: dir.path,
      isAndroid: true,
    );

    test('adds a phone-only export, dedupes the one the PC has', () async {
      final shared = dufs.files.entries.first;
      File('${dir.path}/${shared.key}').writeAsBytesSync(shared.value);
      final onlyHere = utf8
          .decode(dufs.files.entries.last.value)
          .replaceAll('2026-11-09T', '2026-11-08T');
      File(
        '${dir.path}/RunnerUp_2026-11-08-17-30-00_Running.tcx',
      ).writeAsStringSync(onlyHere);
      File('${dir.path}/notes.txt').writeAsStringSync('ignored');

      final report = await importer().runIfNeeded();

      expect(report.failures, isEmpty);
      expect(report.imported, 4);
      expect(report.duplicates, 1);
      final stored = await StorageService.instance.listRuns();
      expect(stored, hasLength(4));
      // The phone-only file is history but is not offered to the PC's list.
      final marker = jsonDecode(dufs.markers.single) as Map<String, dynamic>;
      expect(marker['count'], expectedMarkerNames(dufs.files).length);
    });

    test('an unreadable file warns but never blocks completion', () async {
      final locked = File('${dir.path}/locked_Running.tcx')
        ..writeAsStringSync('x');
      Process.runSync('chmod', ['000', locked.path]);

      final report = await importer().runIfNeeded();

      expect(report.failures, isEmpty);
      expect(dufs.puts, hasLength(1));
    });

    test('a missing folder is fine', () async {
      final report = await RunnerUpImporter(
        client: dufs.client,
        loadLogin: fakeLogin,
        canReadStorage: () async => true,
        localDir: '${dir.path}/missing',
        isAndroid: true,
      ).runIfNeeded();
      expect(report.failures, isEmpty);
      expect(report.imported, 3);
    });
  });

  group('multistatus parsing', () {
    test('keeps tcx names only, decoded, once each', () {
      const xml = '''
<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
<D:response><D:href>/RunnerUp/processed/</D:href></D:response>
<D:response><D:href>/RunnerUp/processed/a%20b_Running.tcx</D:href></D:response>
<D:response><D:href>https://h.test/RunnerUp/processed/C_Walking.TCX</D:href></D:response>
<D:response><D:href>/RunnerUp/processed/C_Walking.TCX</D:href></D:response>
<D:response><D:href>/RunnerUp/processed/a.gpx</D:href></D:response>
<D:response><D:href>/RunnerUp/processed/.hidden.tcx</D:href></D:response>
</D:multistatus>''';
      expect(tcxNamesFromMultistatus(xml), [
        'C_Walking.TCX',
        'a b_Running.tcx',
      ]);
    });

    test('a 207 that is not XML is an error the caller can report', () {
      expect(() => tcxNamesFromMultistatus('<<<'), throwsA(isA<Exception>()));
    });

    test('DavException reads as its sentence', () {
      expect(
        const DavException('GET x answered 500').toString(),
        contains('500'),
      );
    });
  });

  group('DufsCredentials', () {
    test('round-trips through secure storage under the shared keys', () async {
      installFakeSecureStorage();
      expect(await DufsCredentials.load(), isNull);

      await DufsCredentials(
        url: 'https://h.test///',
        user: 'u',
        password: 'p',
      ).save();
      final back = await DufsCredentials.load();

      expect(back!.url, 'https://h.test');
      expect(back.user, 'u');
      expect(back.password, 'p');
      expect(back.authorization, 'Basic ${base64Encode(utf8.encode('u:p'))}');
      expect(
        [kDufsUrlKey, kDufsUserKey, kDufsPasswordKey],
        ['dufs_url', 'dufs_user', 'dufs_password'],
      );
    });

    test('a half-provisioned login is no login', () async {
      installFakeSecureStorage(initial: {kDufsUrlKey: 'https://h.test'});
      expect(await DufsCredentials.load(), isNull);
    });

    test('dufs_login.json needs all three non-empty strings', () {
      expect(
        DufsCredentials.fromJson({'url': 'u', 'user': 'a', 'password': 'b'}),
        isNotNull,
      );
      expect(DufsCredentials.fromJson({'url': 'u', 'user': 'a'}), isNull);
      expect(
        DufsCredentials.fromJson({'url': 'u', 'user': '', 'password': 'b'}),
        isNull,
      );
      expect(
        DufsCredentials.fromJson({'url': 1, 'user': 'a', 'password': 'b'}),
        isNull,
      );
    });
  });
}
