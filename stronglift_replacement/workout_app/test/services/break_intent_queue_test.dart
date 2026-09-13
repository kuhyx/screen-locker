import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';

/// An in-memory [BreakIntentStore] that can also be corrupted on purpose.
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
  late _MemStore store;
  late BreakIntentQueue queue;
  final now = DateTime(2026, 9, 12, 14);

  setUp(() {
    store = _MemStore();
    queue = BreakIntentQueue(store);
  });

  Future<List<BreakIntent>> drainCollecting() async {
    final applied = <BreakIntent>[];
    await queue.drain((intent) async => applied.add(intent));
    return applied;
  }

  test('allocates sequence numbers from one, upward', () async {
    final a = await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    final b = await queue.enqueue(
      kind: BreakIntentKind.skipBreak,
      exIdx: 0,
      setIdx: 1,
      now: now,
    );
    expect(a.seq, 1);
    expect(b.seq, 2);
    expect(store.ints[BreakIntentQueue.seqKey], 2);
  });

  test('applies pending presses oldest first and then prunes them', () async {
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    await queue.enqueue(
      kind: BreakIntentKind.skipBreak,
      exIdx: 0,
      setIdx: 1,
      now: now,
    );

    final applied = await drainCollecting();
    expect(applied.map((i) => i.seq), [1, 2]);
    expect(store.ints[BreakIntentQueue.lastAppliedKey], 2);
    expect(store.lists[BreakIntentQueue.intentsKey], isEmpty);
  });

  test('a second drain applies nothing — presses are exactly-once', () async {
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    expect((await drainCollecting()).length, 1);
    expect(await drainCollecting(), isEmpty);
  });

  // Two presses of the same button are two user actions, not a duplicate.
  test('two identical minusRep presses both apply, in order', () async {
    for (var i = 0; i < 2; i++) {
      await queue.enqueue(
        kind: BreakIntentKind.minusRep,
        exIdx: 0,
        setIdx: 1,
        now: now,
      );
    }
    final applied = await drainCollecting();
    expect(applied.length, 2);
    expect(applied.map((i) => i.seq), [1, 2]);
  });

  test('commits lastApplied per intent, so a crash mid-drain resumes',
      () async {
    for (var i = 0; i < 3; i++) {
      await queue.enqueue(
        kind: BreakIntentKind.done,
        exIdx: 0,
        setIdx: i,
        now: now,
      );
    }
    // Blow up on the second one, as a process death would.
    await expectLater(
      queue.drain((intent) async {
        if (intent.seq == 2) throw StateError('killed mid-drain');
      }),
      throwsStateError,
    );
    expect(store.ints[BreakIntentQueue.lastAppliedKey], 1);

    final applied = await drainCollecting();
    expect(applied.map((i) => i.seq), [2, 3], reason: 'resumes, never replays');
  });

  test('skips an unreadable entry without losing the ones behind it', () async {
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    store.lists[BreakIntentQueue.intentsKey] = [
      'not json',
      ...store.lists[BreakIntentQueue.intentsKey]!,
    ];
    final applied = await drainCollecting();
    expect(applied.map((i) => i.seq), [1]);
    expect(store.lists[BreakIntentQueue.intentsKey], isEmpty);
  });

  test('drops the oldest presses once the queue overflows', () async {
    for (var i = 0; i < BreakIntentQueue.maxEntries + 3; i++) {
      await queue.enqueue(
        kind: BreakIntentKind.done,
        exIdx: 0,
        setIdx: 0,
        now: now,
      );
    }
    final entries = store.lists[BreakIntentQueue.intentsKey]!;
    expect(entries.length, BreakIntentQueue.maxEntries);
    expect(BreakIntent.tryDecode(entries.first)!.seq, 4);
  });

  test('a nudge arriving mid-drain schedules one more pass, not a nested one',
      () async {
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    final applied = <int>[];
    var reentered = false;
    await queue.drain((intent) async {
      applied.add(intent.seq);
      if (reentered) return;
      reentered = true;
      // Arrives while the first drain is still running.
      await queue.enqueue(
        kind: BreakIntentKind.minusRep,
        exIdx: 0,
        setIdx: 0,
        now: now,
      );
      await queue.drain((i) async => applied.add(i.seq));
    });
    expect(applied, [1, 2], reason: 'each press applied exactly once');
  });

  test('an empty queue drains without touching lastApplied', () async {
    expect(await drainCollecting(), isEmpty);
    expect(store.ints[BreakIntentQueue.lastAppliedKey], isNull);
  });

  test('clear forgets pending presses and skips them forever after', () async {
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: now,
    );
    await queue.clear();
    expect(await drainCollecting(), isEmpty);
    expect(store.lists[BreakIntentQueue.intentsKey], isEmpty);
    expect(store.ints[BreakIntentQueue.lastAppliedKey], 1);
  });
}
