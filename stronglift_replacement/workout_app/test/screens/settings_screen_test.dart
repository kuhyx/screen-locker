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

  testWidgets('shows WEIGHTS, TARGET REPS and PROGRESSION THRESHOLDS', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    expect(find.text('WEIGHTS'), findsOneWidget);
    // TARGET REPS and the thresholds below it are off-screen at the test
    // viewport height, so scroll them into view rather than asserting on
    // whatever happens to be built.
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    expect(find.text('TARGET REPS'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    expect(find.text('PROGRESSION THRESHOLDS'), findsOneWidget);
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
          .ancestor(
            of: find.text('30 reps'),
            matching: find.byType(Row),
          )
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

    expect(
      find.textContaining('${before - kWeightIncrement}kg'),
      findsWidgets,
    );
  });

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

  testWidgets('shows links to Sync settings and Advanced sync (GitHub)', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(
      find.text('Sync settings'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Sync settings'), findsOneWidget);
    expect(find.text('Advanced sync (GitHub)'), findsOneWidget);
  });

  testWidgets('opening Sync settings pushes the shared screen', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(
      find.text('Sync settings'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Sync settings'));
    await tester.pumpAndSettle();

    // The shared package's own screen -- its AppBar title, not this app's.
    expect(find.text('Sync settings'), findsOneWidget);
    expect(find.text('Firebase sync'), findsWidgets);
  });

  testWidgets('opening Advanced sync (GitHub) pushes the app-local screen', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(
      find.text('Advanced sync (GitHub)'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('Advanced sync (GitHub)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Advanced sync (GitHub)'));
    await tester.pumpAndSettle();

    expect(find.text('Connect GitHub'), findsOneWidget);
  });

  testWidgets(
    'returning from Sync settings pulls progression and shows a restore banner',
    (tester) async {
      // Regression: connecting is the NORMAL path after a reinstall, because
      // the uninstall wipes the keystore and startup's pull therefore found no
      // account. Without pulling here the device sits on factory defaults
      // while holding real remote progression, and its first finished workout
      // pushes those defaults over the top. Fires on pop rather than inside
      // the shared screen's connect flow -- see _openSyncSettings's doc.
      var pulled = false;
      await _pump(
        tester,
        _wrap(
          progressionPuller: () async {
            pulled = true;
            return const ProgressionSyncResult(
              changed: true,
              count: 7,
              reason: 'restored 7 exercise(s) from Firebase',
            );
          },
        ),
      );
      await tester.scrollUntilVisible(
        find.text('Sync settings'),
        500,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Sync settings'));
      await tester.pumpAndSettle();

      await tester.pageBack();
      await tester.pumpAndSettle();

      expect(pulled, isTrue);
      expect(
        find.text('Restored 7 exercise(s) from Firebase.'),
        findsOneWidget,
      );
    },
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

  testWidgets('changing a success threshold persists it', (tester) async {
    await _pump(tester, _wrap());
    // Scroll to the section header first: the threshold rows below it are not
    // built at all until then, so a `.first` finder for the label would throw
    // "Bad state: No element" before it could match anything.
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    await tester.pumpAndSettle();
    final label = find.text('↑ Increase after N successes').first;
    await tester.scrollUntilVisible(
      label,
      300,
      scrollable: find.byType(Scrollable),
    );
    // The circles (1-5) live in the same Row as the label; tap the "5" circle.
    final row = find.ancestor(of: label, matching: find.byType(Row)).first;
    final five = find.descendant(of: row, matching: find.text('5')).first;
    // The row can sit below the 800x600 test fold — bring the circle fully in.
    await tester.ensureVisible(five);
    await tester.pumpAndSettle();
    // _onThresholdChanged awaits a DB write, so drive it on the real loop.
    await tester.runAsync(() async {
      await tester.tap(five);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final states = await tester.runAsync(
      () => StorageService.instance.getAllExerciseStates(),
    );
    expect(states!.any((s) => s.successThreshold == 5), isTrue);

    // Also exercise the fail-threshold path (onFailChanged closure).
    final failLabel = find.text('↓ Decrease after N failures').first;
    await tester.ensureVisible(failLabel);
    await tester.pumpAndSettle();
    final failRow = find
        .ancestor(of: failLabel, matching: find.byType(Row))
        .first;
    final failFour = find
        .descendant(of: failRow, matching: find.text('4'))
        .first;
    await tester.ensureVisible(failFour);
    await tester.pumpAndSettle();
    await tester.runAsync(() async {
      await tester.tap(failFour);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final states2 = await tester.runAsync(
      () => StorageService.instance.getAllExerciseStates(),
    );
    expect(states2!.any((s) => s.failThreshold == 4), isTrue);
  });

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
