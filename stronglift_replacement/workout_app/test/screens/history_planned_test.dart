// Planned (future-dated) manual workouts in the history view: listed apart
// from what was done, kept off the calendar, and deletable until their day
// through a crdt-sync tombstone.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/calendar_widget.dart';

import '../fake_path_provider.dart';
import '../fake_secure_storage.dart';
import '_history_test_fixtures.dart';

const _pcLog = 'screen-locker-sync/devices/pc/log.json';

Map<String, Object?> _manual(String date, String? start, String source) => {
  'kind': 'manual_workout',
  'type': 'manual_workout',
  'date': date,
  if (start != null) 'start_time': start,
  'source': source,
};

String _log(Map<String, Map<String, Object?>> byId) {
  final hlc = Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'pc');
  return jsonEncode({
    for (final e in byId.entries)
      e.key: Record(id: e.key, fields: {'payload': (e.value, hlc)}).toJson(),
  });
}

/// A GitHub Contents API that remembers what was PUT, so a reload after a
/// delete sees the tombstone. [failPuts] answers every write with a 500.
({http.Client client, Map<String, String> files}) _github(
  Map<String, String> files, {
  bool failPuts = false,
}) {
  final client = MockClient((req) async {
    final path = req.url.path;
    if (!path.contains('/contents/')) return http.Response('{}', 200);
    final key = Uri.decodeComponent(path.split('/contents/').last);
    if (req.method == 'PUT') {
      if (failPuts) return http.Response('boom', 500);
      final body = jsonDecode(req.body) as Map<String, dynamic>;
      files[key] = utf8.decode(base64.decode(body['content'] as String));
      return http.Response('{"content":{"sha":"s"}}', 200);
    }
    final text = files[key];
    if (text != null) {
      return http.Response(
        jsonEncode({'content': base64Encode(utf8.encode(text)), 'sha': 's'}),
        200,
      );
    }
    final children = {
      for (final k in files.keys)
        if (k.startsWith('$key/')) k.substring(key.length + 1).split('/').first,
    };
    if (children.isEmpty) return http.Response('not found', 404);
    return http.Response(
      jsonEncode([
        for (final c in children) {'name': c, 'type': 'dir'},
      ]),
      200,
    );
  });
  return (client: client, files: files);
}

Map<String, String> _seed() => {
  _pcLog: _log({
    'manual:2026-10-14T18:00': _manual('2026-10-14', '18:00', 'squash'),
    'manual:2026-10-16T07:00': _manual('2026-10-16', '07:00', 'swim today'),
    'manual:2026-10-17T10:00': _manual('2026-10-17', '10:00', 'padel'),
    // A future stub has no start time, hence no derivable id: never a plan.
    'manual_workout:2026-10-18': _manual('2026-10-18', null, 'stub'),
  }),
};

DateTime _now() => DateTime(2026, 10, 16, 15);

/// Lets the real-I/O sync calls finish, then rebuilds.
Future<void> _settle(WidgetTester tester, [int rounds = 1]) async {
  for (var i = 0; i < rounds; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();
  }
}

Future<void> _open(
  WidgetTester tester,
  http.Client client, {
  DateTime Function() clock = _now,
}) async {
  tester.view.physicalSize = const Size(500, 3000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await pumpHistory(tester, wrapHistory(httpClient: client, clock: clock));
}

Future<void> _confirmDelete(WidgetTester tester, String button) async {
  await tester.tap(find.byTooltip('Delete planned workout'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(button));
  await tester.pump();
}

Record _phoneRecord(Map<String, String> files, String id) {
  final log =
      jsonDecode(files['screen-locker-sync/devices/phone/log.json']!)
          as Map<String, dynamic>;
  return Record.fromJson(log[id] as Map<String, dynamic>);
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakePathProvider();
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
  });

  testWidgets('a future manual is listed as planned, not as done', (
    tester,
  ) async {
    await _open(tester, _github(_seed()).client);

    // No local sessions, but synced and planned entries still show.
    expect(find.text('No workouts yet.'), findsNothing);
    expect(find.text('PLANNED (not done yet)'), findsOneWidget);
    expect(find.text('2026-10-17 10:00  ·  Planned'), findsOneWidget);
    expect(find.byTooltip('Delete planned workout'), findsOneWidget);
    // Today's entry already happened: done, and not deletable.
    expect(find.text('2026-10-16  ·  Manual'), findsOneWidget);
    expect(find.text('2026-10-14  ·  Manual'), findsOneWidget);
    expect(find.text('2026-10-18  ·  Manual'), findsOneWidget);
    final calendar = tester.widget<WorkoutCalendar>(
      find.byType(WorkoutCalendar),
    );
    expect(calendar.workoutDates, isNot(contains('2026-10-17')));
    expect(calendar.workoutDates, contains('2026-10-16'));
  });

  testWidgets('deleting a plan tombstones it and drops the tile', (
    tester,
  ) async {
    final github = _github(_seed());
    await _open(tester, github.client);

    await _confirmDelete(tester, 'DELETE');
    await _settle(tester, 4);

    final record = _phoneRecord(github.files, 'manual:2026-10-17T10:00');
    expect(record.deleted, isTrue);
    expect(record.deletedHlc, isNotNull);
    // The tile goes only once the reload has read the tombstone back.
    await _settle(tester, 4);
    await tester.pumpAndSettle();
    expect(find.text('PLANNED (not done yet)'), findsNothing);
    expect(find.text('2026-10-17 10:00  ·  Planned'), findsNothing);
  });

  testWidgets('KEEP leaves the plan alone', (tester) async {
    final github = _github(_seed());
    await _open(tester, github.client);

    await _confirmDelete(tester, 'KEEP');
    await _settle(tester);

    expect(
      github.files.containsKey('screen-locker-sync/devices/phone/log.json'),
      isFalse,
    );
    expect(find.text('2026-10-17 10:00  ·  Planned'), findsOneWidget);
  });

  testWidgets('a failed delete keeps the tile and says why', (tester) async {
    await _open(tester, _github(_seed(), failPuts: true).client);

    await _confirmDelete(tester, 'DELETE');
    await _settle(tester, 2);

    expect(find.textContaining('Not deleted — push failed'), findsOneWidget);
    expect(find.text('2026-10-17 10:00  ·  Planned'), findsOneWidget);
  });

  testWidgets('a delete confirmed once the day has started is refused', (
    tester,
  ) async {
    var now = _now();
    final github = _github(_seed());
    await _open(tester, github.client, clock: () => now);

    await tester.tap(find.byTooltip('Delete planned workout'));
    await tester.pumpAndSettle();
    now = DateTime(2026, 10, 17, 0, 1);
    await tester.tap(find.text('DELETE'));
    await tester.pump();
    await _settle(tester, 2);

    expect(find.textContaining('no longer a planned workout'), findsOneWidget);
    expect(
      github.files.containsKey('screen-locker-sync/devices/phone/log.json'),
      isFalse,
    );
    // Reloaded against the new day: it is done now, not planned.
    await tester.pumpAndSettle();
    expect(find.text('2026-10-17  ·  Manual'), findsOneWidget);
  });
}
