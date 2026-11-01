import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

final String _name = workoutA.first.name;
const _key = 'last_workout_type';

Future<void> _freshStore() async {
  StorageService.resetForTesting();
  await StorageService.init();
}

Future<Map<String, dynamic>> _row(String table, String id) async {
  final rows = ((await _svc.exportData())[table] as List)
      .cast<Map<String, dynamic>>();
  return rows.firstWhere((r) => (r['name'] ?? r['key']) == id);
}

/// A version-2 file carrying one exercise row and one setting row.
Map<String, dynamic> _file({
  required double weight,
  required String type,
  required int stamp,
  required Map<String, dynamic> exerciseBase,
}) => {
  'format': kExportFormat,
  'version': 2,
  'exercise_state': [
    {...exerciseBase, 'weight': weight, 'updated_at': stamp},
  ],
  'settings': [
    {'key': _key, 'value': type, 'updated_at': stamp},
  ],
};

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(_freshStore);

  Future<Map<String, dynamic>> localEdited() async {
    await _svc.setExerciseWeight(_name, 40);
    await _svc.setLastWorkoutType('A');
    return await _row('exercise_state', _name);
  }

  test('export is version 2 and rows carry updated_at', () async {
    final data = await _svc.exportData();
    expect(data['version'], 2);
    expect(
      (await _row('exercise_state', _name)).containsKey('updated_at'),
      true,
    );
  });

  test('a newer file row replaces the local row (both tables)', () async {
    final base = await localEdited();
    final future = (base['updated_at']! as int) + 100000;

    final written = await _svc.importData(
      _file(weight: 99, type: 'B', stamp: future, exerciseBase: base),
    );

    expect(written, 2);
    expect((await _svc.getExerciseState(_name))!.weight, 99);
    expect(await _svc.getNextWorkoutType(), 'A');
    expect((await _row('exercise_state', _name))['updated_at'], future);
    expect((await _row('settings', _key))['updated_at'], future);
  });

  test('an older file row loses to the local row (both tables)', () async {
    final base = await localEdited();

    final written = await _svc.importData(
      _file(weight: 99, type: 'B', stamp: 1, exerciseBase: base),
    );

    expect(written, 0);
    expect((await _svc.getExerciseState(_name))!.weight, 40);
    expect(await _svc.getNextWorkoutType(), 'B');
  });

  test('a tie keeps the local row', () async {
    final base = await localEdited();
    final tie = base['updated_at']! as int;

    final written = await _svc.importData(
      _file(weight: 99, type: 'B', stamp: tie, exerciseBase: base),
    );

    expect(written, 0);
    expect((await _svc.getExerciseState(_name))!.weight, 40);
  });

  test(
    'a seeded default (updated_at 0) loses to any stamped file row',
    () async {
      final base = await _row('exercise_state', _name);
      await _svc.importData(
        _file(weight: 77, type: 'B', stamp: 5, exerciseBase: base),
      );
      expect((await _svc.getExerciseState(_name))!.weight, 77);
    },
  );

  group('a version 1 file (no updated_at) keeps the old rule', () {
    Map<String, dynamic> v1(Map<String, dynamic> base) => {
      'format': kExportFormat,
      'version': 1,
      'exercise_state': [
        {...base, 'weight': 88.0}..remove('updated_at'),
      ],
      'settings': [
        {'key': _key, 'value': 'B'},
      ],
    };

    test('applies on a freshly installed store', () async {
      final base = await _row('exercise_state', _name);
      final written = await _svc.importData(v1(base));
      expect(written, greaterThan(0));
      expect((await _svc.getExerciseState(_name))!.weight, 88);
      expect(await _svc.getNextWorkoutType(), 'A');
    });

    test('never clobbers a store that has local data', () async {
      final base = await localEdited();
      await _svc.importData(v1(base));
      expect((await _svc.getExerciseState(_name))!.weight, 40);
      expect(await _svc.getNextWorkoutType(), 'B');
    });
  });

  test('importing a v2 file twice is the same as once', () async {
    final base = await localEdited();
    final future = (base['updated_at']! as int) + 100000;
    final file = _file(
      weight: 99,
      type: 'B',
      stamp: future,
      exerciseBase: base,
    );
    await _svc.importData(file);
    expect(await _svc.importData(file), 0);
  });
}
