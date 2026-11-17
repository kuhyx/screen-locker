import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_launch.dart';

import '../fake_run_service.dart';

void main() {
  test('no run owed: home as usual, the service is left alone', () async {
    final client = FakeForegroundRunClient();
    expect(
      await resumeRunOnLaunch(owed: () async => false, client: client),
      isFalse,
    );
    expect(client.calls, isEmpty);
  });

  test('a run owed opens the run and brings its service back', () async {
    final client = FakeForegroundRunClient();
    expect(
      await resumeRunOnLaunch(owed: () async => true, client: client),
      isTrue,
    );
    expect(client.calls, ['start']);
    expect(client.starts, [true]);
  });

  test('a service that will not start still opens the run screen', () async {
    final client = FakeForegroundRunClient(startSucceeds: false);
    expect(
      await resumeRunOnLaunch(owed: () async => true, client: client),
      isTrue,
    );
  });

  test('a platform without services just opens the run', () async {
    final client = FakeForegroundRunClient(isSupported: false);
    expect(
      await resumeRunOnLaunch(owed: () async => true, client: client),
      isTrue,
    );
    expect(client.calls, isEmpty);
  });
}
