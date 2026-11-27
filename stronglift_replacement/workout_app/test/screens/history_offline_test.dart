/// Offline-first history: local rows show at once, never behind the network.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:material_ui/material_ui.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_secure_storage.dart';
import '_history_test_fixtures.dart';

/// A backend that never answers: the phone is offline, or the network hangs.
http.Client _hangingRemote() =>
    MockClient((_) => Completer<http.Response>().future);

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
  });

  testWidgets('local sessions show while the remote read hangs', (
    tester,
  ) async {
    await seedSession(tester, jsonEncode({'exercises': <Object>[]}));

    await pumpHistory(tester, wrapHistory(httpClient: _hangingRemote()));

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('A  ·  2024-06-01'), findsWidgets);
  });

  testWidgets('synced PC rows from the last read show while offline', (
    tester,
  ) async {
    final pcRow = find.byKey(const ValueKey('synced-2026-07-13-Run'));
    await pumpHistory(tester, wrapHistory(httpClient: historySyncMock()));
    await tester.pumpWidget(const SizedBox());

    await pumpHistory(tester, wrapHistory(httpClient: _hangingRemote()));
    await tester.scrollUntilVisible(
      pcRow,
      200,
      scrollable: find.byType(Scrollable).first,
    );

    expect(pcRow, findsOneWidget);
  });
}
