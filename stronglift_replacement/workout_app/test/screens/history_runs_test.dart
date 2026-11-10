// Runs in the history: the overview strip, the one-entry-per-run merge with
// the PC's runnerup_verified rows, the calendar, and opening the detail.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/screens/run_detail_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/widgets/calendar_widget.dart';

import '../fake_secure_storage.dart';
import '../widgets/_run_map_fixtures.dart';
import '_history_test_fixtures.dart';

// historySyncMock() holds a PC run and a PC manual workout, both dated this.
final _pcDay = DateTime(2026, 7, 13, 12);

Future<void> _seedRun(
  WidgetTester tester,
  DateTime startedAt, {
  RunSport sport = RunSport.running,
}) async {
  final track = buildTrack(
    startedAt: startedAt.toUtc(),
    sport: sport,
    count: 3,
  );
  await tester.runAsync(
    () => StorageService.instance.insertRun(
      track,
      tcxFilename: 'run_${track.id}.tcx',
      tcxSha256: tcxSha256(encodeTcx(track)),
      uploadState: RunUploadState.pending,
    ),
  );
}

Future<void> _pump(WidgetTester tester, {bool withPc = false}) async {
  if (withPc) installFakeSecureStorage(initial: {'sync.token': 'tok'});
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
  await pumpHistory(
    tester,
    wrapHistory(
      httpClient: withPc ? historySyncMock() : null,
      tileProviderOpener: fakeTiles(),
    ),
  );
}

Future<void> _scrollToSynced(WidgetTester tester) => tester.scrollUntilVisible(
  find.text('SYNCED FROM PC'),
  200,
  scrollable: find.byType(Scrollable).first,
);

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

  testWidgets('runs alone are history: no empty state, a tile per run', (
    tester,
  ) async {
    await _seedRun(tester, DateTime(2026, 7, 13, 12));
    await _seedRun(tester, DateTime(2026, 7, 14, 12), sport: RunSport.walking);
    await _pump(tester);
    expect(find.text('No workouts yet.'), findsNothing);
    expect(find.byKey(const Key('runs_strip')), findsOneWidget);
    expect(find.text('5.20'), findsNWidgets(2));
    expect(find.text('32:10'), findsNWidgets(2));
    expect(find.text('14.07'), findsOneWidget);
    expect(find.byIcon(Icons.directions_walk), findsOneWidget);
  });

  testWidgets('no runs: no strip', (tester) async {
    await _pump(tester);
    expect(find.byKey(const Key('runs_strip')), findsNothing);
  });

  testWidgets('the local run replaces the PC entry of its day, once', (
    tester,
  ) async {
    await _seedRun(tester, _pcDay);
    await _pump(tester, withPc: true);
    await _scrollToSynced(tester);
    // The PC's manual workout of that day stays; its run entry is gone.
    expect(find.textContaining('2026-07-13  ·  Manual'), findsOneWidget);
    expect(find.textContaining('2026-07-13  ·  Run'), findsNothing);
    expect(find.text('5.20'), findsOneWidget);
  });

  testWidgets('a run on another day leaves the PC entry visible', (
    tester,
  ) async {
    await _seedRun(tester, DateTime(2026, 7, 20, 12));
    await _pump(tester, withPc: true);
    await _scrollToSynced(tester);
    expect(find.textContaining('2026-07-13  ·  Run'), findsOneWidget);
    expect(find.text('5.20'), findsOneWidget);
  });

  testWidgets('a run marks its day on the calendar', (tester) async {
    await _seedRun(tester, DateTime(2026, 7, 13, 12));
    await _pump(tester);
    final calendar = tester.widget<WorkoutCalendar>(
      find.byType(WorkoutCalendar),
    );
    expect(calendar.workoutDates, contains('2026-07-13'));
  });

  testWidgets('tapping a run opens its detail, back returns', (tester) async {
    await _seedRun(tester, DateTime(2026, 7, 13, 12));
    await _pump(tester);
    await tester.tap(find.text('5.20'));
    await tester.pumpAndSettle();
    // getRun is real sqflite: let it finish on the real event loop.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pumpAndSettle();
    expect(find.byType(RunDetailScreen), findsOneWidget);
    expect(find.text('2026-07-13 12:00'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();
    expect(find.byType(RunDetailScreen), findsNothing);
    expect(find.byKey(const Key('runs_strip')), findsOneWidget);
  });

  testWidgets('a run deleted before the tap lands opens nothing', (
    tester,
  ) async {
    await _seedRun(tester, DateTime(2026, 7, 13, 12));
    await _pump(tester);
    await tester.runAsync(
      () => StorageService.instance.deleteRun(
        RunTrack.idFor(DateTime(2026, 7, 13, 12).toUtc()),
      ),
    );
    await tester.tap(find.text('5.20'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pumpAndSettle();
    expect(find.byType(RunDetailScreen), findsNothing);
  });
}
