// The SANDBOX section: present only in the sandbox flavor, and each of its
// three controls acts on the (sandbox's) database and reports back.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/sandbox/sandbox.dart';
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
    Sandbox.enabled = true;
    Sandbox.restSecs = Sandbox.defaultRestSecs;
  });
  tearDown(() {
    Sandbox.enabled = false;
    Sandbox.restSecs = Sandbox.defaultRestSecs;
  });

  Widget wrap() => MaterialApp(
    theme: buildAppTheme(),
    home: SettingsScreen(
      firebaseFactory: () async => null,
      sessionProbe: () async => false,
      storageChecker: () async => false,
      progressionPuller: () async =>
          const ProgressionSyncResult(changed: false, reason: 'stubbed'),
    ),
  );

  Future<void> pump(WidgetTester tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    // The list, explicitly: the section's own TextField is a Scrollable too,
    // and scrolling that one never brings the header into view.
    await tester.scrollUntilVisible(
      find.text('SANDBOX'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
  }

  Future<void> tapReal(WidgetTester tester, Finder f) async {
    // A status line appearing below the row can push the row's button out
    // of the viewport between taps.
    await tester.ensureVisible(f);
    await tester.runAsync(() async {
      await tester.tap(f);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
  }

  testWidgets('is absent from the daily build', (tester) async {
    Sandbox.enabled = false;
    await tester.runAsync(() async {
      await tester.pumpWidget(wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    expect(find.text('SANDBOX'), findsNothing);
  });

  testWidgets('wipe resets the database and the rest override', (tester) async {
    // DB writes run on the real loop: under the test zone's fake clock a
    // sqflite-ffi call never completes.
    await tester.runAsync(() async {
      await StorageService.instance.setSandboxRestSecs(30);
      await StorageService.instance.saveActiveSession({'workoutType': 'A'});
    });
    Sandbox.restSecs = 30;
    await pump(tester);
    await tapReal(tester, find.text('Wipe sandbox data'));
    expect(find.textContaining('Wiped —'), findsOneWidget);
    expect(Sandbox.restSecs, Sandbox.defaultRestSecs);
    final active = await tester.runAsync(
      StorageService.instance.loadActiveSession,
    );
    expect(active, isNull);
  });

  testWidgets('mark today not done reports what it removed', (tester) async {
    await pump(tester);
    await tapReal(tester, find.text('Mark today not done'));
    expect(find.textContaining('Nothing logged today'), findsOneWidget);

    final today = DateTime.now().toIso8601String().substring(0, 10);
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: today,
        workoutType: 'A',
        durationSeconds: 1,
        succeeded: true,
        json: '{}',
      ),
    );
    await tapReal(tester, find.text('Mark today not done'));
    expect(find.textContaining('Removed 1 workout'), findsOneWidget);
  });

  testWidgets('rest length: rejects junk, persists a whole number', (
    tester,
  ) async {
    await pump(tester);
    final field = find.byKey(const Key('sandbox-rest-secs'));
    await tester.enterText(field, 'abc');
    await tapReal(tester, find.text('Save'));
    expect(find.textContaining('whole number of seconds'), findsOneWidget);
    expect(Sandbox.restSecs, Sandbox.defaultRestSecs);

    await tester.enterText(field, '0');
    await tapReal(tester, find.text('Save'));
    expect(find.textContaining('whole number of seconds'), findsOneWidget);

    await tester.enterText(field, '45');
    await tapReal(tester, find.text('Save'));
    expect(find.text('Every rest now lasts 45 s.'), findsOneWidget);
    expect(Sandbox.restSecs, 45);
    final saved = await tester.runAsync(
      () => StorageService.instance.getSandboxRestSecs(5),
    );
    expect(saved, 45);
  });
}
