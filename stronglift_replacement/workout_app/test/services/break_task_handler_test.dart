import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/break_service_port.dart';
import 'package:workout_app/services/break_task_handler.dart';

import '../fake_break_service.dart';

class _MemStore implements BreakIntentStore {
  final ints = <String, int>{};
  final lists = <String, List<String>>{};

  @override
  Future<int> readInt(String key) async => ints[key] ?? 0;

  @override
  Future<void> writeInt(String key, int value) async => ints[key] = value;

  @override
  Future<List<String>> readStringList(String key) async =>
      lists[key] ?? const [];

  @override
  Future<void> writeStringList(String key, List<String> value) async =>
      lists[key] = List.of(value);
}

void main() {
  final now = DateTime(2026, 9, 12, 14);

  late FakeBreakServicePort port;
  late _MemStore store;
  late BreakIntentQueue queue;
  late BreakTaskHandler handler;

  setUp(() {
    port = FakeBreakServicePort();
    store = _MemStore();
    queue = BreakIntentQueue(store);
    handler = BreakTaskHandler(port, queue);
  });

  Map<String, Object?> snapMap({
    int breakEndMs = 0,
    int breakDurationSecs = 180,
    int nextExIdx = 0,
    int nextSetIdx = 1,
    int lastExIdx = 0,
    int lastSetIdx = 0,
    int breakForExIdx = 0,
    int breakForSetIdx = 0,
    int setsRemaining = 4,
  }) => BreakSnapshot(
    workoutType: 'A',
    breakEndMs: breakEndMs,
    breakDurationSecs: breakDurationSecs,
    breakLabel: 'Rest (3 min — well done!)',
    breakForExIdx: breakForExIdx,
    breakForSetIdx: breakForSetIdx,
    nextExIdx: nextExIdx,
    nextSetIdx: nextSetIdx,
    nextExName: 'Squat',
    nextSetNumber: nextSetIdx + 1,
    nextTotalSets: 5,
    nextReps: 5,
    nextWeight: 40,
    lastExIdx: lastExIdx,
    lastSetIdx: lastSetIdx,
    setsRemaining: setsRemaining,
  ).toMap();

  Future<List<BreakIntent>> queued() async {
    final raw = await store.readStringList(BreakIntentQueue.intentsKey);
    return [for (final e in raw) BreakIntent.tryDecode(e)!];
  }

  test('start registers plugins before anything else touches them', () async {
    await handler.start(snapMap(), now);
    expect(port.ready, isTrue);
    expect(port.drawn, hasLength(1));
  });

  test('redraws only when the words actually changed', () async {
    final endMs = now.add(const Duration(seconds: 90)).millisecondsSinceEpoch;
    await handler.start(snapMap(breakEndMs: endMs), now);
    final afterStart = port.drawn.length;

    // Same displayed second, twice: one redraw, not two.
    await handler.tick(now);
    await handler.tick(now.add(const Duration(milliseconds: 300)));
    expect(port.drawn.length, afterStart);

    await handler.tick(now.add(const Duration(seconds: 1)));
    expect(port.drawn.length, afterStart + 1);
  });

  test('alerts once when the rest ends, not every tick after', () async {
    final endMs = now.add(const Duration(seconds: 5)).millisecondsSinceEpoch;
    await handler.start(snapMap(breakEndMs: endMs), now);

    await handler.tick(now.add(const Duration(seconds: 4)));
    expect(port.alerts, 0);

    await handler.tick(now.add(const Duration(seconds: 5)));
    await handler.tick(now.add(const Duration(seconds: 6)));
    await handler.tick(now.add(const Duration(seconds: 30)));
    expect(port.alerts, 1);
  });

  test('a new rest period alerts again', () async {
    final first = now.add(const Duration(seconds: 5)).millisecondsSinceEpoch;
    await handler.start(snapMap(breakEndMs: first), now);
    await handler.tick(now.add(const Duration(seconds: 5)));
    expect(port.alerts, 1);

    final second = now.add(const Duration(seconds: 60)).millisecondsSinceEpoch;
    await handler.receiveData(snapMap(breakEndMs: second), now);
    await handler.tick(now.add(const Duration(seconds: 60)));
    expect(port.alerts, 2);
  });

  test('tick before any snapshot does nothing', () async {
    await handler.tick(now);
    expect(port.drawn, isEmpty);
    expect(port.alerts, 0);
  });

  group('button presses', () {
    test('Done queues the next set and nudges the UI', () async {
      await handler.start(snapMap(nextExIdx: 1, nextSetIdx: 2), now);
      await handler.pressButton(BreakNotificationAction.done, now);

      final intents = await queued();
      expect(intents, hasLength(1));
      expect(intents.single.kind, BreakIntentKind.done);
      expect(intents.single.exIdx, 1);
      expect(intents.single.setIdx, 2);
      expect(port.nudges, 1);
    });

    test('− 1 rep targets the set recorded last, resolved at press time',
        () async {
      await handler.start(snapMap(lastExIdx: 2, lastSetIdx: 3), now);
      await handler.pressButton(BreakNotificationAction.minusRep, now);

      final intents = await queued();
      expect(intents.single.kind, BreakIntentKind.minusRep);
      expect(intents.single.exIdx, 2);
      expect(intents.single.setIdx, 3);
    });

    test('− 1 rep stretches a running rest to the failure length', () async {
      final endMs = now.add(const Duration(seconds: 120)).millisecondsSinceEpoch;
      await handler.start(
        snapMap(breakEndMs: endMs, breakDurationSecs: 180),
        now,
      );
      await handler.pressButton(BreakNotificationAction.minusRep, now);

      final s = handler.snapshot!;
      expect(s.breakDurationSecs, 300);
      expect(s.breakLabel, contains('5 min'));
      // Re-cut from the original start: 60s in, so 240s left of 300.
      expect(
        DateTime.fromMillisecondsSinceEpoch(s.breakEndMs)
            .difference(now)
            .inSeconds,
        240,
      );
    });

    test('Skip break clears the rest immediately', () async {
      final endMs = now.add(const Duration(seconds: 90)).millisecondsSinceEpoch;
      await handler.start(snapMap(breakEndMs: endMs), now);
      await handler.pressButton(BreakNotificationAction.skipBreak, now);

      expect((await queued()).single.kind, BreakIntentKind.skipBreak);
      expect(handler.snapshot!.hasBreak, isFalse);
    });

    test('Done on the last set stops the service instead of carrying on',
        () async {
      await handler.start(snapMap(setsRemaining: 1), now);
      await handler.pressButton(BreakNotificationAction.done, now);
      expect(port.stopped, isTrue);
    });

    test('ignores presses that no longer refer to anything', () async {
      await handler.start(
        snapMap(nextExIdx: -1, nextSetIdx: -1, lastExIdx: -1, lastSetIdx: -1),
        now,
      );
      await handler.pressButton(BreakNotificationAction.done, now);
      await handler.pressButton(BreakNotificationAction.minusRep, now);
      await handler.pressButton(BreakNotificationAction.skipBreak, now);
      await handler.pressButton('something_else', now);
      expect(await queued(), isEmpty);
      expect(port.nudges, 0);
    });

    test('ignores a press before any snapshot arrived', () async {
      await handler.pressButton(BreakNotificationAction.done, now);
      expect(await queued(), isEmpty);
    });

    test('− 1 rep outside a rest queues without touching the clock', () async {
      await handler.start(snapMap(lastExIdx: 0, lastSetIdx: 0), now);
      await handler.pressButton(BreakNotificationAction.minusRep, now);
      expect((await queued()).single.kind, BreakIntentKind.minusRep);
      expect(handler.snapshot!.hasBreak, isFalse);
    });

    test('− 1 rep during a WARMUP rest leaves the clock alone', () async {
      final endMs = now.add(const Duration(seconds: 90)).millisecondsSinceEpoch;
      await handler.start(
        snapMap(breakEndMs: endMs, breakForSetIdx: -1, lastSetIdx: 0),
        now,
      );
      await handler.pressButton(BreakNotificationAction.minusRep, now);
      expect(handler.snapshot!.breakEndMs, endMs);
    });
  });

  group('bad payloads', () {
    test('a non-map payload leaves the previous state showing', () async {
      await handler.start(snapMap(), now);
      final before = handler.snapshot;
      await handler.receiveData('not a map', now);
      expect(handler.snapshot, same(before));
    });

    test('a malformed map leaves the previous state showing', () async {
      await handler.start(snapMap(), now);
      final before = handler.snapshot;
      await handler.receiveData(<String, Object?>{'workoutType': 'A'}, now);
      expect(handler.snapshot, same(before));
    });

    test('start with no payload draws nothing but still registers', () async {
      await handler.start(null, now);
      expect(port.ready, isTrue);
      expect(port.drawn, isEmpty);
    });
  });
}
