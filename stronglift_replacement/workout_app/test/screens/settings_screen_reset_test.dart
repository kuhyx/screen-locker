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

  testWidgets(
    'returning from Sync settings with nothing changed shows no banner',
    (tester) async {
      await _pump(tester, _wrap());
      await tester.scrollUntilVisible(
        find.text('Sync settings'),
        500,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Sync settings'));
      await tester.pumpAndSettle();

      await tester.pageBack();
      await tester.pumpAndSettle();

      expect(find.textContaining('Restored'), findsNothing);
    },
  );

  testWidgets('reps change is debounced then written to storage', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    await tester.pumpAndSettle();

    // Situp defaults to 30 reps and is the only exercise at that value.
    final minus = find.descendant(
      of: find
          .ancestor(of: find.text('30 reps'), matching: find.byType(Row))
          .first,
      matching: find.byIcon(Icons.remove),
    );
    // Same 600ms debounce as weights: run on the real loop so the timer fires.
    await tester.runAsync(() async {
      await tester.tap(minus);
      await Future<void>.delayed(const Duration(milliseconds: 800));
    });
    await tester.pump();

    final after = (await tester.runAsync(
      () => StorageService.instance.getExerciseState('Situp'),
    ))!.reps;
    expect(after, 29, reason: 'the decrement must reach storage');
  });

  testWidgets('weight change is debounced then written to storage', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    final name = workoutA.first.name;
    final before = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!.weight;

    // Tapping "+" schedules a 600ms debounce Timer; running the tap and the
    // wait on the real loop lets the timer fire and setExerciseWeight complete.
    await tester.runAsync(() async {
      await tester.tap(find.byIcon(Icons.add).first);
      await Future<void>.delayed(const Duration(milliseconds: 800));
    });
    await tester.pump();

    final after = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!.weight;
    expect(after, before + kWeightIncrement);
  });
}
