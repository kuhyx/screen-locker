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

  testWidgets('threshold circles show values 1-5', (tester) async {
    await _pump(tester, _wrap());
    // The threshold cards sit below WEIGHTS and TARGET REPS, past the test
    // viewport's fold, so they are not built until scrolled to.
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    await tester.pumpAndSettle();
    for (int i = 1; i <= 5; i++) {
      expect(find.text('$i'), findsWidgets);
    }
  });

  testWidgets('Reset dialog shows on tap and cancels', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Reset to defaults?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Reset to defaults?'), findsNothing);
  });

  testWidgets('Reset dialog confirms and resets data', (tester) async {
    await tester.runAsync(
      () =>
          StorageService.instance.setExerciseWeight(workoutA.first.name, 99.0),
    );

    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Reset'));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(workoutA.first.name),
    );
    expect(state!.weight, workoutA.first.weight);
  });

  testWidgets('offline backup offers a grant button when not held', (
    tester,
  ) async {
    var asked = false;
    await _pump(
      tester,
      _wrap(
        storageChecker: () async => false,
        storageRequester: () async {
          asked = true;
          return true;
        },
      ),
    );
    await tester.scrollUntilVisible(
      find.text('Grant storage permission'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    // Framed as optional: Firebase restores progression without it.
    expect(
      find.textContaining('Optional.', skipOffstage: false),
      findsOneWidget,
    );

    await tester.tap(find.text('Grant storage permission'));
    await tester.pumpAndSettle();

    expect(asked, isTrue, reason: 'the grant page is opened on demand only');
    expect(find.text('Storage permission granted'), findsOneWidget);
    expect(find.text('Grant storage permission'), findsNothing);
  });

  testWidgets('offline backup reports an already-granted permission', (
    tester,
  ) async {
    await _pump(tester, _wrap(storageChecker: () async => true));
    await tester.scrollUntilVisible(
      find.text('Storage permission granted'),
      500,
      scrollable: find.byType(Scrollable).first,
    );

    expect(find.text('Storage permission granted'), findsOneWidget);
    expect(find.text('Grant storage permission'), findsNothing);
    expect(
      find.textContaining('Granted.', skipOffstage: false),
      findsOneWidget,
    );
  });
}
