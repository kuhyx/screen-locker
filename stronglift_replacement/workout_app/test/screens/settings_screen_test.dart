import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_secure_storage.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
  });

  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  Widget _wrap({
    http.Client? httpClient,
    Future<FirebaseRestClient?> Function()? firebaseFactory,
    Future<FirebaseRestClient?> Function()? googleFirebaseFactory,
    bool? googleAvailable,
    Future<FirebaseAccount?> Function()? accountLoader,
    Future<void> Function(FirebaseAccount)? accountSaver,
    Future<void> Function()? accountClearer,
    Future<bool> Function()? sessionProbe,
    Future<bool> Function()? storageChecker,
    Future<bool> Function()? storageRequester,
    Future<ProgressionSyncResult> Function()? progressionPuller,
  }) => MaterialApp(
    theme: buildAppTheme(),
    home: SettingsScreen(
      httpClient: httpClient,
      // Injected so the widget never reaches the OS keystore, which
      // `flutter test` has no platform-channel binding for.
      firebaseFactory: firebaseFactory ?? () async => null,
      googleFirebaseFactory: googleFirebaseFactory,
      googleAvailable: googleAvailable,
      accountLoader: accountLoader ?? () async => null,
      accountSaver: accountSaver,
      accountClearer: accountClearer,
      // Defaults to whatever the injected account says, so a test that only
      // stubs the account still describes one coherent device. The production
      // probe reads the keystore this harness deliberately avoids, and would
      // otherwise answer "no session" for a device the test declared signed
      // in.
      sessionProbe:
          sessionProbe ??
          () async => await (accountLoader ?? () async => null)() != null,
      // Same reason: permission_handler is a platform channel too.
      storageChecker: storageChecker ?? () async => false,
      storageRequester: storageRequester,
      // Default to a no-op pull: opening/closing Sync settings triggers one,
      // and the real service would open a database and hit the network from
      // a widget test.
      progressionPuller:
          progressionPuller ??
          () async => const ProgressionSyncResult(
            changed: false,
            reason: 'stubbed in tests',
          ),
    ),
  );

  testWidgets('shows Settings app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('shows WEIGHTS, TARGET REPS and PER EXERCISE', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('WEIGHTS'), findsOneWidget);
    // TARGET REPS and the per-exercise list below it are off-screen at the test
    // viewport height, so scroll them into view rather than asserting on
    // whatever happens to be built.
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    expect(find.text('TARGET REPS'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('PER EXERCISE'), 200);
    expect(find.text('PER EXERCISE'), findsOneWidget);
  });

  testWidgets('increment reps button increases the target reps', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    await tester.pumpAndSettle();
    // Situp defaults to 30 reps and is the only exercise at that value.
    expect(find.text('30 reps'), findsOneWidget);
    final plus = find.descendant(
      of: find
          .ancestor(of: find.text('30 reps'), matching: find.byType(Row))
          .first,
      matching: find.byIcon(Icons.add),
    );
    await tester.tap(plus);
    await tester.pumpAndSettle();
    expect(find.text('31 reps'), findsOneWidget);
  });

  testWidgets('shows all exercise names from both workout plans', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    for (final ex in [...workoutA, ...workoutB]) {
      expect(find.text(ex.name), findsWidgets);
    }
  });

  testWidgets('Reset defaults button is present', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Reset defaults'), findsOneWidget);
  });

  testWidgets('increment weight button increases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    // DB reads need the real event loop (the widget-test zone fakes async).
    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(firstName),
    );
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pump();

    expect(find.textContaining('${before + kWeightIncrement}kg'), findsWidgets);
  });

  testWidgets('decrement weight button decreases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    // DB reads need the real event loop (the widget-test zone fakes async).
    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(firstName),
    );
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.remove).first);
    await tester.pump();

    expect(find.textContaining('${before - kWeightIncrement}kg'), findsWidgets);
  });
}
