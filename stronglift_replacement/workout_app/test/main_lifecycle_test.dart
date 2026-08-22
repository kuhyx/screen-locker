// The lifecycle observer that starts and stops the phone's HTTP socket.
//
// Linux returns early because main() never starts the socket there, so a
// resume must not start one behind the lock screen's back.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/main.dart';
import 'package:workout_app/services/storage_service.dart';

import 'fake_secure_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    // The widget-test host has no Android sqflite plugin; the FFI factory
    // drives the same schema, as everywhere else in this suite.
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
  });

  testWidgets('every lifecycle transition is handled without throwing', (
    tester,
  ) async {
    await tester.pumpWidget(const WorkoutApp());
    await tester.pump();

    // Drives didChangeAppLifecycleState for each state the switch names.
    for (final state in AppLifecycleState.values) {
      tester.binding.handleAppLifecycleStateChanged(state);
      await tester.pump();
    }

    expect(tester.takeException(), isNull);
  });
}
