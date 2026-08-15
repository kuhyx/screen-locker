// Shared fixtures for the home-screen test files.
//
// The four fakes all subclass WorkoutSyncService and override `syncNow` — a
// real override, not an extension member, because extension methods dispatch
// statically and a fake could not intercept one.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';

// runAsync steps outside FakeAsync so real I/O (NetworkInterface.list) completes.
Future<void> pumpHome(WidgetTester tester, Widget w) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(w);
    // Small real delay lets sqflite + NetworkInterface.list complete.
    await Future<void>.delayed(const Duration(milliseconds: 200));
  });
  await tester.pump();
}

// The home screen syncs in the background on every open. Left to itself
// that reaches FlutterSecureStorage, whose platform channel throws under
// `flutter test`, so every test here would fail on a MissingPluginException
// that has nothing to do with what it is asserting. Report "not
// configured" instead: no credentials means no sync tick is attempted.
Widget wrapHome({Future<bool> Function()? configuredProbe}) => MaterialApp(
  theme: buildAppTheme(),
  home: HomeScreen(
    configuredProbe: configuredProbe ?? () async => false,
    clock: () => DateTime(2026, 8, 15, 18),
  ),
);

/// A sync service whose tick always fails, with a reason worth showing.
class FailingSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() async =>
      const PushResult(pushed: false, reason: 'sync failed: no network');
}

/// A sync service whose tick always succeeds.
class OkSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() async =>
      const PushResult(pushed: true, reason: 'synced');
}

/// A sync service whose tick never resolves, holding the card on whatever
/// the persisted state said — which is how a real slow network behaves.
class HangingSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() => Completer<PushResult>().future;
}

/// A sync service that counts how many ticks it was asked for.
class CountingSyncService extends WorkoutSyncService {
  CountingSyncService(this.onTick);

  /// Called once per [syncNow].
  final void Function() onTick;

  @override
  Future<PushResult> syncNow() async {
    onTick();
    // Fail, so the card keeps offering Retry instead of collapsing to the
    // button-less healthy state after the first tick.
    return const PushResult(pushed: false, reason: 'sync failed: offline');
  }
}
