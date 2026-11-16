import 'dart:async' show unawaited;

// Framework material, for `showDialog` only: material_ui ships its own
// MaterialLocalizations type, so a package that still calls the framework
// `showDialog` (crdt_sync_flutter did) finds none under WorkoutApp and throws
// a null check. This opens one through the real app root.
// ignore: deprecated_member_use, the only source of the framework dialog.
import 'package:flutter/material.dart' as fw show showDialog;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/main.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/storage_service.dart';

import 'fake_secure_storage.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    installFakeSecureStorage();
    StorageService.resetForTesting();
    await StorageService.init();
  });

  Future<BuildContext> pumpApp(WidgetTester tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(const WorkoutApp());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    return tester.element(find.byType(HomeScreen));
  }

  testWidgets('a material_ui dialog opens through the app root', (
    tester,
  ) async {
    final context = await pumpApp(tester);
    unawaited(
      showDialog<void>(
        context: context,
        builder: (_) => const AlertDialog(key: Key('mui-dialog')),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('mui-dialog')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a framework dialog opens through the app root', (tester) async {
    final context = await pumpApp(tester);
    unawaited(
      fw.showDialog<void>(
        context: context,
        builder: (_) => const SizedBox(key: Key('fw-dialog')),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('fw-dialog')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
