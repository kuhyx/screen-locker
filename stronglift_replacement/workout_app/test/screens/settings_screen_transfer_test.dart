// The export/import buttons in Settings reload the screen after an import.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/data_transfer_buttons.dart';

import '../fake_pc_pairing.dart';
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

  testWidgets('Settings shows the buttons and reloads after an import', (
    tester,
  ) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: SettingsScreen(
            pcPairingLoader: fakePcPairing,
            firebaseFactory: () async => null,
            sessionProbe: () async => false,
            storageChecker: () async => false,
            progressionPuller: () async =>
                const ProgressionSyncResult(changed: false, reason: 'stubbed'),
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    final buttons = find.byType(DataTransferButtons);
    await tester.scrollUntilVisible(buttons, 300);
    expect(find.bySemanticsLabel('Export data'), findsOneWidget);
    expect(find.bySemanticsLabel('Import data'), findsOneWidget);

    tester.widget<DataTransferButtons>(buttons).onImported!();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pump();

    expect(find.byType(DataTransferButtons), findsOneWidget);
  });
}
