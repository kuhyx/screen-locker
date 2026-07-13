import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/services/storage_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  // runAsync steps outside FakeAsync so real I/O (NetworkInterface.list) completes.
  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      // Small real delay lets sqflite + NetworkInterface.list complete.
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
  }

  Widget _wrap() => const MaterialApp(home: HomeScreen());

  testWidgets('shows Workout Tracker app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Workout Tracker'), findsOneWidget);
  });

  testWidgets('shows Next: Workout A when no workout done', (tester) async {
    await _pump(tester, _wrap());
    expect(find.textContaining('Next: Workout A'), findsOneWidget);
  });

  testWidgets('shows Start Workout A button', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Start Workout A'), findsOneWidget);
  });

  testWidgets('history icon navigates to history screen', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Progress'), findsOneWidget);
  });

  testWidgets('settings icon navigates to settings screen', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('"Done for today" message shows after saving a session today',
      (tester) async {
    final today = DateTime.now();
    final dateStr =
        '${today.year}-${today.month.toString().padLeft(2, '0')}'
        '-${today.day.toString().padLeft(2, '0')}';
    // DB writes need the real event loop (the widget-test zone fakes async and
    // would hang sqflite-ffi); run the seed inside runAsync.
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: dateStr,
        workoutType: 'A',
        durationSeconds: 1800,
        succeeded: true,
        json: '{"exercises":[]}',
      ),
    );
    await _pump(tester, _wrap());
    expect(find.text('Done for today!'), findsOneWidget);
  });

  testWidgets('HTTP sync tile renders', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('HTTP sync (no ADB needed)'), findsOneWidget);
  });
}
