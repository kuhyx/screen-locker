// Shared fixtures for the history-screen test files.
//
// These four were local functions inside `main()`. That is the shape that
// silently breaks a split: both halves get a copy of the preamble, but the
// second half's references resolve against the wrong closure. Hoisted to
// top level so each split file imports one definition.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

Future<void> pumpHistory(WidgetTester tester, Widget w) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(w);
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await tester.pump();
}

/// Wraps the history screen with sync pinned to a known state.
///
/// [firebaseFactory] defaults to "no account", which is what makes these
/// tests independent of the machine they run on. Faking the sync token is not
/// enough on its own: the guard also asks Firebase whether an account exists,
/// and on a desktop holding a cached refresh token the real factory says yes,
/// so the fetch escapes to the network and the test fails with a
/// RemoteSyncError that has nothing to do with the screen.
Widget wrapHistory({
  http.Client? httpClient,
  Future<FirebaseRestClient?> Function()? firebaseFactory,
}) => MaterialApp(
  theme: buildAppTheme(),
  home: HistoryScreen(
    httpClient: httpClient,
    firebaseFactory: firebaseFactory ?? () async => null,
  ),
);

/// A GitHub mock serving one PC device log holding a run and a manual.
http.Client historySyncMock() {
  String file(String body) => jsonEncode({
    'content': base64Encode(utf8.encode(body)),
    'sha': 'sha',
  });
  Record rec(String id, String kind, int ms) => Record(
    id: id,
    fields: {
      'payload': (
        {
          'kind': kind,
          'date': '2026-07-13',
          'source': 'Running: 9.8 km in 55 min',
        },
        Hlc(wallTimeMs: ms, counter: 0, nodeId: 'pc'),
      ),
    },
  );
  final log = jsonEncode({
    'runnerup_verified:2026-07-13': rec(
      'runnerup_verified:2026-07-13',
      'runnerup_verified',
      2000,
    ).toJson(),
    'manual:2026-07-13T14:00': rec(
      'manual:2026-07-13T14:00',
      'manual_workout',
      1000,
    ).toJson(),
  });
  return MockClient((req) async {
    final path = req.url.path;
    if (path.endsWith('screen-locker-sync/devices')) {
      return http.Response(
        jsonEncode([
          {'name': 'pc', 'type': 'dir'},
        ]),
        200,
      );
    }
    if (path.contains('pc/log.json')) {
      return http.Response(file(log), 200);
    }
    return http.Response('not found', 404);
  });
}

// Seed a workout. DB writes must run on the real event loop: the widget-test
// zone fakes async, so a sqflite-ffi write in the test body hangs (then the
// isolate crashes on shutdown). runAsync gives the write the real loop.
Future<void> seedSession(
  WidgetTester tester,
  String json, {
  String date = '2024-06-01',
  String type = 'A',
  int duration = 1800,
  bool succeeded = true,
}) async {
  await tester.runAsync(
    () => StorageService.instance.saveSession(
      date: date,
      workoutType: type,
      durationSeconds: duration,
      succeeded: succeeded,
      json: json,
    ),
  );
}
