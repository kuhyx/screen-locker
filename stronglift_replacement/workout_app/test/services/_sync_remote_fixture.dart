// A stateful sync remote for the offline-first tests: PUTs land, later GETs
// see them, and `down` makes every request fail like a dead network.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;

import '_sync_test_fixtures.dart';

/// A GitHub Contents API double whose PUTs land, so a later GET sees them.
class FakeRemote {
  final files = <String, String>{};
  final logPuts = <Map<String, dynamic>>[];
  bool down = false;

  http.Client client() => http_testing.MockClient((request) async {
    if (down) throw http.ClientException('offline');
    final path = request.url.path;
    if (!path.contains('/contents/')) return syncResponse(200);
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      final text = utf8.decode(base64.decode(body['content'] as String));
      files[key] = text;
      if (key.endsWith('log.json')) {
        logPuts.add(jsonDecode(text) as Map<String, dynamic>);
      }
      return syncResponse(200, {'content': <String, dynamic>{}});
    }
    if (key == 'screen-locker-sync/devices') {
      final devices = {
        for (final k in files.keys)
          if (k.startsWith('screen-locker-sync/devices/')) k.split('/')[2],
      };
      return syncResponse(200, [
        for (final d in devices) {'name': d, 'type': 'dir'},
      ]);
    }
    final text = files[key];
    return text == null ? syncResponse(404) : fileContaining(text);
  });
}

Record pcRunRecord() => Record(
  id: 'runnerup_verified:2026-07-13',
  fields: {
    'payload': (
      {'kind': 'runnerup_verified', 'date': '2026-07-13'},
      Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'pc'),
    ),
  },
);
