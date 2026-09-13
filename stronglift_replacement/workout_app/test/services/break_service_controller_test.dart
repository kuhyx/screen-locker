import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/break_service_controller.dart';
import 'package:workout_app/services/foreground_break_client.dart';

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

const _snapshot = BreakSnapshot(
  workoutType: 'A',
  breakEndMs: 0,
  breakDurationSecs: 0,
  breakLabel: '',
  breakForExIdx: -1,
  breakForSetIdx: -1,
  nextExIdx: 0,
  nextSetIdx: 0,
  nextExName: 'Squat',
  nextSetNumber: 1,
  nextTotalSets: 5,
  nextReps: 5,
  nextWeight: 40,
  lastExIdx: -1,
  lastSetIdx: -1,
  setsRemaining: 5,
);

void main() {
  late FakeForegroundBreakClient client;
  late _MemStore store;
  late BreakIntentQueue queue;
  late BreakServiceController controller;

  setUp(() {
    client = FakeForegroundBreakClient();
    store = _MemStore();
    queue = BreakIntentQueue(store);
    controller = BreakServiceController(client, queue);
  });

  Future<BreakServiceStartResult> start() =>
      controller.start(_snapshot, onDrainNudge: () {});

  test('starts and reports success when the permission is already held',
      () async {
    expect(await start(), BreakServiceStartResult.started);
    expect(controller.isStarted, isTrue);
    expect(client.calls, ['init', 'hasPermission', 'listen', 'start']);
  });

  test('asks for the permission when it is not held yet', () async {
    client.permissionGranted = false;
    expect(await start(), BreakServiceStartResult.started);
    expect(client.calls, contains('requestPermission'));
  });

  // A denied permission must NOT block the service: its isolate still holds
  // the wake lock and still plays the break-end sound. Only the visible
  // surface is lost, and the caller is told so it can say so on screen.
  test('still starts when the permission is denied, and says so', () async {
    client
      ..permissionGranted = false
      ..grantOnRequest = false;
    expect(await start(), BreakServiceStartResult.startedWithoutNotification);
    expect(controller.isStarted, isTrue);
  });

  test('reports failure and stops listening when the service refuses to start',
      () async {
    client.startSucceeds = false;
    expect(await start(), BreakServiceStartResult.failed);
    expect(controller.isStarted, isFalse);
    expect(client.calls.last, 'unlisten');
  });

  test('does nothing at all on a platform with no foreground service',
      () async {
    client.isSupported = false;
    expect(await start(), BreakServiceStartResult.unsupported);
    expect(client.calls, isEmpty);
    expect(controller.isStarted, isFalse);
  });

  test('push is a no-op until the service has started', () async {
    await controller.push(_snapshot);
    expect(client.calls, isEmpty);

    await start();
    await controller.push(_snapshot);
    expect(client.calls, contains('push'));
  });

  test('stop tears the service down and forgets pending presses', () async {
    await start();
    await queue.enqueue(
      kind: BreakIntentKind.done,
      exIdx: 0,
      setIdx: 0,
      now: DateTime(2026, 9, 12),
    );

    await controller.stop();
    expect(controller.isStarted, isFalse);
    expect(client.calls, contains('stop'));
    expect(store.lists[BreakIntentQueue.intentsKey], isEmpty);

    final applied = <BreakIntent>[];
    await controller.drain((i) async => applied.add(i));
    expect(applied, isEmpty);
  });

  test('stop is inert on an unsupported platform', () async {
    client.isSupported = false;
    await controller.stop();
    expect(client.calls, isEmpty);
  });

  // No notification means no button to press, so the queue's storage -- which
  // needs a platform SharedPreferences -- must never be touched there.
  test('drain never reads storage on an unsupported platform', () async {
    client.isSupported = false;
    var applied = 0;
    await controller.drain((_) async => applied++);
    expect(applied, 0);
    expect(store.lists, isEmpty);
    expect(store.ints, isEmpty);
  });

  test('drain applies queued presses once the service is running', () async {
    await start();
    await queue.enqueue(
      kind: BreakIntentKind.minusRep,
      exIdx: 1,
      setIdx: 2,
      now: DateTime(2026, 9, 12),
    );
    final applied = <BreakIntent>[];
    await controller.drain((i) async => applied.add(i));
    expect(applied.single.exIdx, 1);
    expect(applied.single.setIdx, 2);
  });

  test('the registered nudge callback is the one the caller passed', () async {
    var nudged = 0;
    await controller.start(_snapshot, onDrainNudge: () => nudged++);
    client.onNudge!();
    expect(nudged, 1);
  });

  // The service is meant to outlive its screen -- the back button pops the
  // workout while it carries on, and stopWithTask="false" survives a swipe.
  // That makes a startup reaper the only thing standing between a crash and a
  // notification counting down a workout that ended hours ago.
  group('stopStaleBreakService', () {
    test('stops a service whose workout no longer exists', () async {
      client.running = true;
      final stopped = await stopStaleBreakService(
        client,
        hasActiveWorkout: () async => false,
      );
      expect(stopped, isTrue);
      expect(client.calls, contains('stop'));
    });

    test('leaves a service alone while its workout is still in progress',
        () async {
      client.running = true;
      final stopped = await stopStaleBreakService(
        client,
        hasActiveWorkout: () async => true,
      );
      expect(stopped, isFalse);
      expect(client.calls, isNot(contains('stop')));
    });

    test('does nothing when no service is running', () async {
      client.running = false;
      expect(
        await stopStaleBreakService(client, hasActiveWorkout: () async => false),
        isFalse,
      );
      expect(client.calls, isNot(contains('stop')));
    });

    test('does nothing on a platform with no foreground service', () async {
      client
        ..isSupported = false
        ..running = true;
      expect(
        await stopStaleBreakService(client, hasActiveWorkout: () async => false),
        isFalse,
      );
      expect(client.calls, isEmpty);
    });
  });
}
