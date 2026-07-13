import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/http_server_service.dart';

void main() {
  group('HttpServerService', () {
    tearDown(() async {
      await HttpServerService.instance.stop();
    });

    test('is a singleton', () {
      expect(
        identical(HttpServerService.instance, HttpServerService.instance),
        isTrue,
      );
    });

    test('latestWorkout getter returns null initially', () {
      expect(HttpServerService.instance.latestWorkout, isNull);
    });

    test('latestWorkout setter updates the value', () {
      HttpServerService.instance.latestWorkout = '{"test":1}';
      expect(HttpServerService.instance.latestWorkout, '{"test":1}');
    });

    test('start binds and stop releases the server', () async {
      await HttpServerService.instance.start();
      // A second start call is a no-op (idempotent).
      await HttpServerService.instance.start();
      await HttpServerService.instance.stop();
      // Calling stop when already stopped is safe.
      await HttpServerService.instance.stop();
    });

    test('localAddresses returns a list', () async {
      final addrs = await HttpServerService.instance.localAddresses;
      expect(addrs, isA<List<String>>());
    });

    test('kWorkoutServerPort has expected value', () {
      expect(kWorkoutServerPort, 8765);
    });

    test('start swallows a bind failure when the port is taken', () async {
      final blocker = await ServerSocket.bind(
        InternetAddress.anyIPv4,
        kWorkoutServerPort,
      );
      // Binding fails (SocketException) but start() must not throw.
      await HttpServerService.instance.start();
      await blocker.close();
    });

    test('serves the latest workout over HTTP', () async {
      HttpServerService.instance.resetForTesting();
      await HttpServerService.instance.start();
      final client = HttpClient();

      Future<int> get(String path) async {
        final req = await client.get('localhost', kWorkoutServerPort, path);
        final resp = await req.close();
        await resp.drain<void>();
        return resp.statusCode;
      }

      expect(await get('/workout'), 404); // no data yet
      HttpServerService.instance.latestWorkout = '{"workout_type":"A"}';
      expect(await get('/workout'), 200);
      expect(await get('/other'), 404); // unknown path
      client.close();
    });
  });
}
