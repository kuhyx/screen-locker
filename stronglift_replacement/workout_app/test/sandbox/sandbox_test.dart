import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/sandbox/sandbox.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  void answer(Object? Function(MethodCall call)? handler) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          Sandbox.channel,
          handler == null ? null : (call) async => handler(call),
        );
  }

  final printed = <String>[];
  setUp(() {
    printed.clear();
    debugPrint = (String? message, {int? wrapWidth}) => printed.add(message ?? '');
    Sandbox.enabled = false;
    Sandbox.restSecs = Sandbox.defaultRestSecs;
  });
  tearDown(() {
    debugPrint = debugPrintThrottled;
    answer(null);
    Sandbox.enabled = false;
  });

  test('init takes the flavor from MainActivity', () async {
    answer((call) => call.method == 'isSandbox');
    await Sandbox.init();
    expect(Sandbox.enabled, isTrue);
  });

  test('init treats a null answer as the daily build', () async {
    answer((_) => null);
    await Sandbox.init();
    expect(Sandbox.enabled, isFalse);
  });

  test('init falls back to the environment where there is no channel', () async {
    answer(null);
    await Sandbox.init({Sandbox.envVar: '1'});
    expect(Sandbox.enabled, isTrue);
    expect(printed.single, contains('WORKOUT_SANDBOX=1: sandbox'));

    await Sandbox.init({});
    expect(Sandbox.enabled, isFalse);
    expect(printed.last, contains('unset: daily build'));
  });

  test('init reads the real environment by default', () async {
    answer(null);
    await Sandbox.init();
    // Whatever the host env says, it must not throw and must report it.
    expect(printed.single, contains('no sandbox channel'));
  });

  test('rest and label pass through for the daily build', () {
    expect(Sandbox.rest(180), 180);
    expect(Sandbox.restLabel('Rest (3 min — well done!)'), 'Rest (3 min — well done!)');
  });

  test('rest and label are overridden in the sandbox', () {
    Sandbox.enabled = true;
    Sandbox.restSecs = 9;
    expect(Sandbox.rest(180), 9);
    expect(Sandbox.restLabel('Rest (3 min — well done!)'), 'Rest (9 s — sandbox)');
  });
}
