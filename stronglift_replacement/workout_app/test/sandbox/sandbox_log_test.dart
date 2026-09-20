import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final printed = <String>[];
  final sent = <MethodCall>[];

  void channelUp() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(Sandbox.channel, (call) async {
          sent.add(call);
          return null;
        });
  }

  setUp(() {
    printed.clear();
    sent.clear();
    debugPrint = (String? message, {int? wrapWidth}) => printed.add(message ?? '');
    SandboxLog.resetForTesting();
    Sandbox.enabled = true;
  });
  tearDown(() {
    debugPrint = debugPrintThrottled;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(Sandbox.channel, null);
    Sandbox.enabled = false;
  });

  test('is silent in the daily build', () async {
    Sandbox.enabled = false;
    channelUp();
    SandboxLog.event('tap set', {'set': 1});
    await Future<void>.delayed(Duration.zero);
    expect(printed, isEmpty);
    expect(sent, isEmpty);
  });

  test('prints and forwards one line per event', () async {
    channelUp();
    SandboxLog.event('break start', {'secs': 5});
    SandboxLog.event('break end');
    await Future<void>.delayed(Duration.zero);
    expect(printed, ['WorkoutSandbox: break start {secs: 5}', 'WorkoutSandbox: break end']);
    expect(sent.map((c) => c.method), ['log', 'log']);
    expect(sent.first.arguments, 'break start {secs: 5}');
  });

  test('says once that logcat is unreachable, then keeps printing', () async {
    SandboxLog.event('one');
    await Future<void>.delayed(Duration.zero);
    SandboxLog.event('two');
    await Future<void>.delayed(Duration.zero);
    expect(printed.where((l) => l.contains('logcat channel unavailable')), hasLength(1));
    expect(printed.where((l) => l == 'WorkoutSandbox: two'), hasLength(1));
  });
}
