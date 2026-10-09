// The PC LINK section: shows the pairing, validates and persists the host.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/sandbox/sandbox_http.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/pc_pairing.dart';
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
  tearDown(() => SandboxHttpOverrides.pokeHost = null);

  Widget wrap(PcPairingState pairing) => MaterialApp(
    theme: buildAppTheme(),
    home: SettingsScreen(
      pcPairingLoader: () async => pairing,
      firebaseFactory: () async => null,
      sessionProbe: () async => false,
      storageChecker: () async => false,
      progressionPuller: () async =>
          const ProgressionSyncResult(changed: false, reason: 'stubbed'),
    ),
  );

  Future<void> pump(WidgetTester tester, PcPairingState pairing) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(wrap(pairing));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.scrollUntilVisible(
      find.byKey(const Key('pc-paired')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
  }

  Future<void> save(WidgetTester tester, String host) async {
    await tester.enterText(find.byKey(const Key('pc-host')), host);
    final button = find.byKey(const Key('pc-host-save'));
    await tester.ensureVisible(button);
    await tester.runAsync(() async {
      await tester.tap(button);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
  }

  String pairedLine(WidgetTester tester) =>
      tester.widget<Text>(find.byKey(const Key('pc-paired'))).data!;

  testWidgets('a paired phone shows the host and a check', (tester) async {
    await pump(
      tester,
      PcPairingState(host: '192.168.1.43', keyHex: 'c3' * 32),
    );
    expect(find.text('PC LINK'), findsOneWidget);
    expect(pairedLine(tester), 'PC paired ✓');
    final field = tester.widget<TextField>(find.byKey(const Key('pc-host')));
    expect(field.controller!.text, '192.168.1.43');
  });

  testWidgets('an unpaired phone names the pairing script', (tester) async {
    await pump(tester, const PcPairingState(host: '10.0.0.2'));
    expect(pairedLine(tester), contains('run scripts/pair_phone.sh'));
  });

  testWidgets('a junk host is refused and nothing is saved', (tester) async {
    await pump(tester, const PcPairingState(host: '10.0.0.2'));
    await save(tester, 'not a host');
    expect(
      find.text('Not an IPv4 address or hostname: "not a host".'),
      findsOneWidget,
    );
    final saved = await tester.runAsync(StorageService.instance.getPcHost);
    expect(saved, isNull);
    expect(SandboxHttpOverrides.pokeHost, isNull);
  });

  testWidgets('a valid host is persisted and moves the exception', (
    tester,
  ) async {
    await pump(tester, const PcPairingState(host: '10.0.0.2'));
    await save(tester, '  192.168.1.77 ');
    expect(
      find.text('Workouts are now sent to 192.168.1.77:$kPcPokePort.'),
      findsOneWidget,
    );
    final saved = await tester.runAsync(StorageService.instance.getPcHost);
    expect(saved, '192.168.1.77');
    expect(SandboxHttpOverrides.pokeHost, '192.168.1.77');
  });
}
