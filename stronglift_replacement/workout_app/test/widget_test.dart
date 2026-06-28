import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/main.dart';
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

  testWidgets('WorkoutApp renders HomeScreen', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(const WorkoutApp());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    expect(find.text('Workout Tracker'), findsOneWidget);
  });
}
