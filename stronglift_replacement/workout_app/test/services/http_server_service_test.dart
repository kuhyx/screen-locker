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
  });
}
