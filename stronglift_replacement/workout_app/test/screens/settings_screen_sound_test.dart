// The Settings sound switch: one switch for every cue, remembered.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_pc_pairing.dart';
import '../fake_secure_storage.dart';

Widget _settings() => MaterialApp(
  theme: buildAppTheme(),
  home: SettingsScreen(
    pcPairingLoader: fakePcPairing,
    firebaseFactory: () async => null,
    accountLoader: () async => null,
    sessionProbe: () async => false,
    storageChecker: () async => false,
    progressionPuller: () async =>
        const ProgressionSyncResult(changed: false, reason: 'stubbed'),
  ),
);

Future<void> _pump(WidgetTester tester) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(_settings());
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await tester.pump();
}

// The section sits below the fold and is built lazily, so it only starts
// reading its stored value once scrolled to; give that read time to land.
Future<void> _reveal(WidgetTester tester) async {
  await tester.scrollUntilVisible(_switch, 200);
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 200)),
  );
  await tester.pump();
}

Finder get _switch => find.widgetWithText(SwitchListTile, 'Sound');

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

  testWidgets('sound ships on', (tester) async {
    await _pump(tester);
    await _reveal(tester);
    expect(tester.widget<SwitchListTile>(_switch).value, isTrue);
  });

  testWidgets('flipping it off is stored and survives a restart', (
    tester,
  ) async {
    await _pump(tester);
    await _reveal(tester);
    await tester.runAsync(() async {
      await tester.tap(_switch);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
    expect(tester.widget<SwitchListTile>(_switch).value, isFalse);
    expect(
      await tester.runAsync(() => StorageService.instance.getSoundEnabled()),
      isFalse,
    );

    // "Restart": a brand new screen over the same database.
    await tester.pumpWidget(const SizedBox());
    await _pump(tester);
    await _reveal(tester);
    expect(tester.widget<SwitchListTile>(_switch).value, isFalse);
  });

  testWidgets('and back on again', (tester) async {
    await tester.runAsync(
      () => StorageService.instance.setSoundEnabled(enabled: false),
    );
    await _pump(tester);
    await _reveal(tester);
    expect(tester.widget<SwitchListTile>(_switch).value, isFalse);
    await tester.runAsync(() async {
      await tester.tap(_switch);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
    expect(
      await tester.runAsync(() => StorageService.instance.getSoundEnabled()),
      isTrue,
    );
  });
}
