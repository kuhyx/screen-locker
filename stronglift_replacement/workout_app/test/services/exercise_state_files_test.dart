import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/exercise_state_files.dart';
import 'package:workout_app/services/storage_service.dart';

void main() {
  late Directory tmp;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    tmp = Directory.systemTemp.createTempSync('esf_');
  });

  tearDown(() => tmp.deleteSync(recursive: true));

  group('writeDeloadExport', () {
    test('writes every dir it can', () async {
      final a = Directory(p.join(tmp.path, 'a'));
      final b = Directory(p.join(tmp.path, 'b'));
      await ExerciseStateFiles(
        exportDirs: () async => [a, b],
      ).writeDeloadExport('{"x":1}');
      for (final d in [a, b]) {
        expect(
          File(p.join(d.path, kDeloadExportFileName)).readAsStringSync(),
          '{"x":1}',
        );
      }
    });

    test('one unwritable dir is tolerated, none is fatal', () async {
      final blocker = File(p.join(tmp.path, 'file'))..writeAsStringSync('');
      final bad = Directory(p.join(blocker.path, 'sub'));
      final good = Directory(p.join(tmp.path, 'good'));
      await ExerciseStateFiles(
        exportDirs: () async => [bad, good],
      ).writeDeloadExport('{}');
      await expectLater(
        ExerciseStateFiles(
          exportDirs: () async => [bad],
        ).writeDeloadExport('{}'),
        throwsA(isA<FileSystemException>()),
      );
      await expectLater(
        ExerciseStateFiles(exportDirs: () async => []).writeDeloadExport('{}'),
        throwsA(isA<FileSystemException>()),
      );
    });
  });

  group('importRestoreFile', () {
    final lift = workoutA.first.name;

    test('imports a pushed file once and keeps it renamed', () async {
      final row = Map<String, Object?>.of(
        (await StorageService.instance.exportData())['exercise_state']
            .cast<Map<String, Object?>>()
            .firstWhere((Map<String, Object?> r) => r['name'] == lift),
      );
      row['weight'] = 12.5;
      row['updated_at'] = DateTime.now().millisecondsSinceEpoch + 1000;
      File(p.join(tmp.path, kRestoreFileName)).writeAsStringSync(
        jsonEncode({
          'version': 3,
          'exercise_state': [row],
        }),
      );
      final files = ExerciseStateFiles(restoreDir: () async => tmp);
      final r = await files.importRestoreFile();
      expect(r.rows, 1);
      expect((await StorageService.instance.getExerciseState(lift))!.weight, 12.5);
      expect(File(p.join(tmp.path, kRestoreFileName)).existsSync(), isFalse);
      expect((await files.importRestoreFile()).rows, 0);
    });

    test('a broken file is left in place', () async {
      final f = File(p.join(tmp.path, kRestoreFileName))
        ..writeAsStringSync('not json');
      final r = await ExerciseStateFiles(
        restoreDir: () async => tmp,
      ).importRestoreFile();
      expect(r.rows, 0);
      expect(f.existsSync(), isTrue);
    });

    test('no dir on this platform', () async {
      final r = await ExerciseStateFiles(
        restoreDir: () async => null,
      ).importRestoreFile();
      expect(r.rows, 0);
    });
  });
}
