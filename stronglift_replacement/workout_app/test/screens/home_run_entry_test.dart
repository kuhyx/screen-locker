// The run icon on the home screen opens the run screen.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
import '../fake_geolocator.dart';
import '../fake_secure_storage.dart';
import '_home_test_fixtures.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    // The run screen reads its last pace target from shared_preferences.
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
    // The real run controller asks the real source where the user is.
    final original = GeolocatorPlatform.instance;
    GeolocatorPlatform.instance = FakeGeolocator();
    addTearDown(() => GeolocatorPlatform.instance = original);
  });

  testWidgets('the run icon opens the run screen and back returns home', (
    tester,
  ) async {
    await pumpHome(tester, wrapHome());
    expect(find.byKey(const Key('home_run')), findsOneWidget);

    await tester.tap(find.byKey(const Key('home_run')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byType(RunScreen), findsOneWidget);
    expect(find.byKey(const Key('run_start')), findsOneWidget);

    tester.state<NavigatorState>(find.byType(Navigator)).pop();
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsNothing);
    expect(find.byKey(const Key('home_run')), findsOneWidget);
    // Home reloads on return; let its database reads finish on the real loop.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump(const Duration(minutes: 2));
  });
}
