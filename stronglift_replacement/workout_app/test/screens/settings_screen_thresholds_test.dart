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
}
