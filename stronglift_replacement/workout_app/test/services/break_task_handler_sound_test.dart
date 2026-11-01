// The foreground-service isolate honours the sound switch it is told about.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_task_handler.dart';

import '../fake_break_service.dart';
import '_break_task_handler_fixtures.dart';

void main() {
  final now = DateTime(2026, 11, 1, 14);
  final endMs = now.add(const Duration(seconds: 5)).millisecondsSinceEpoch;

  Future<FakeBreakServicePort> alertWith({required bool soundOn}) async {
    final port = FakeBreakServicePort();
    final handler = BreakTaskHandler(port, BreakIntentQueue(MemIntentStore()));
    await handler.start(snapMap(breakEndMs: endMs, soundOn: soundOn), now);
    await handler.tick(now.add(const Duration(seconds: 5)));
    return port;
  }

  test('sound on: the alert is told to ring', () async {
    final port = await alertWith(soundOn: true);
    expect(port.alertSounds, [true]);
  });

  test('sound off: the alert still fires, told to stay silent', () async {
    final port = await alertWith(soundOn: false);
    expect(port.alertSounds, [false], reason: 'heads-up and buzz remain');
  });
}
