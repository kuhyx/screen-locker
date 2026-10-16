// readManualLedger: the manual payloads plus every tombstoned id, which the
// form needs to refuse re-logging onto a deleted record.
//
// Split from workout_sync_read_test.dart for the 250-line cap.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;

import '../fake_secure_storage.dart';
import '_sync_test_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('readManualLedger', () {
    test('returns live manuals and every tombstoned id', () async {
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final deleted = Record(
        id: 'manual:gone',
        fields: const {},
        deleted: true,
        deletedHlc: Hlc(wallTimeMs: 3000, counter: 0, nodeId: 'phone'),
      );
      final phoneLog = jsonEncode({'manual:gone': deleted.toJson()});
      final pcLog = jsonEncode({
        'manual:a': manualRecord('manual:a', 'NEW', 2000).toJson(),
        // Live on the PC, deleted on the phone: the tombstone wins.
        'manual:gone': manualRecord('manual:gone', 'X', 1000).toJson(),
      });
      final (:httpClient, putCalls: _) = mockGitHub(
        contentResponses: {
          'screen-locker-sync/devices': syncResponse(200, [
            {'name': 'phone'},
            {'name': 'pc'},
          ]),
          'screen-locker-sync/devices/phone/log.json': fileContaining(phoneLog),
          'screen-locker-sync/devices/pc/log.json': fileContaining(pcLog),
        },
      );
      final ledger = await syncService(
        httpClient: httpClient,
      ).readManualLedger();
      expect(ledger.payloads.map((p) => p['cost']), ['NEW']);
      expect(ledger.tombstoned, {'manual:gone'});
    });

    test('is empty without a token', () async {
      installFakeSecureStorage();
      final (:httpClient, putCalls: _) = mockGitHub();
      final ledger = await syncService(
        httpClient: httpClient,
      ).readManualLedger();
      expect(ledger.payloads, isEmpty);
      expect(ledger.tombstoned, isEmpty);
    });

    test('is empty when the backend fails', () async {
      installFakeSecureStorage(initial: {'sync.token': 'tok'});
      final httpClient = http_testing.MockClient(
        (request) async => http.Response('', 500),
      );
      final ledger = await syncService(
        httpClient: httpClient,
      ).readManualLedger();
      expect(ledger.payloads, isEmpty);
      expect(ledger.tombstoned, isEmpty);
    });
  });
}
