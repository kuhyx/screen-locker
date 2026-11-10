// The display-only position watch behind the idle map.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/idle_location.dart';
import 'package:workout_app/services/position_source.dart';

import '../run_test_fixtures.dart';

/// A source whose permission answer the test releases by hand.
class _SlowSource extends ManualPositionSource {
  final gate = Completer<LocationAccess>();

  @override
  Future<LocationAccess> requestAccess() => gate.future;
}

void main() {
  late ManualPositionSource source;
  late List<LocationAccess> heard;
  late IdleLocation idle;

  IdleLocation build(PositionSource s) => IdleLocation(s, onAccess: heard.add);

  setUp(() {
    source = ManualPositionSource();
    heard = [];
    idle = build(source);
  });

  tearDown(() => idle.dispose());

  test('granted: reports it, watches, and follows each fix', () async {
    expect(idle.access, isNull);
    await idle.open();
    expect(heard, [LocationAccess.granted]);
    expect(idle.access, LocationAccess.granted);
    expect(source.subscriptions, 1);

    source.controller.add(fixAt(0, 0));
    await pumpEventQueue();
    expect(idle.position.value!.latitude, closeTo(fixAt(0, 0).latitude, 1e-9));
    source.controller.add(fixAt(2, 30));
    await pumpEventQueue();
    expect(idle.position.value!.latitude, closeTo(fixAt(2, 30).latitude, 1e-9));
  });

  test('opening twice keeps a single stream', () async {
    await idle.open();
    await idle.open();
    expect(source.subscriptions, 1);
  });

  test('refused: reports it, no stream, no position', () async {
    source.access = LocationAccess.deniedForever;
    await idle.open();
    expect(heard, [LocationAccess.deniedForever]);
    expect(source.subscriptions, 0);
    expect(idle.position.value, isNull);
  });

  test('recheck never prompts; a grant starts the watch', () async {
    source.access = LocationAccess.denied;
    await idle.open();
    source.access = LocationAccess.granted;
    await idle.recheck();
    expect(source.requests, 1);
    expect(source.checks, 1);
    expect(source.subscriptions, 1);
    expect(heard.last, LocationAccess.granted);
  });

  test(
    'recheck after a revocation ends the watch and clears the dot',
    () async {
      await idle.open();
      source.controller.add(fixAt(0, 0));
      await pumpEventQueue();
      expect(source.controller.hasListener, isTrue);

      source.access = LocationAccess.deniedForever;
      await idle.recheck();
      expect(idle.position.value, isNull);
      expect(source.controller.hasListener, isFalse);
      expect(heard.last, LocationAccess.deniedForever);
    },
  );

  test('stop ends the watch and later rechecks are ignored', () async {
    await idle.open();
    await idle.stop();
    expect(source.controller.hasListener, isFalse);
    await idle.recheck();
    expect(source.checks, 0);
  });

  test('open after stop watches again (the retry after a refusal)', () async {
    await idle.open();
    await idle.stop();
    await idle.open();
    expect(source.subscriptions, 2);
    expect(source.controller.hasListener, isTrue);
  });

  test('an answer that lands after stop is dropped', () async {
    final slow = _SlowSource();
    idle = build(slow);
    final opening = idle.open();
    await idle.stop();
    slow.gate.complete(LocationAccess.granted);
    await opening;
    expect(heard, isEmpty);
    expect(slow.subscriptions, 0);
  });

  test('a stream error is logged, not thrown, and the dot stays', () async {
    await idle.open();
    source.controller.add(fixAt(0, 0));
    await pumpEventQueue();
    source.controller.addError(StateError('gps off'));
    await pumpEventQueue();
    expect(idle.position.value, isNotNull);
    source.controller.add(fixAt(2, 6));
    await pumpEventQueue();
    expect(idle.position.value!.latitude, closeTo(fixAt(2, 6).latitude, 1e-9));
  });
}
