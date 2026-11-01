import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  test('sound ships on: nothing stored means enabled', () async {
    expect(await _svc.getSoundEnabled(), isTrue);
  });

  test('turning sound off and on again is remembered', () async {
    await _svc.setSoundEnabled(enabled: false);
    expect(await _svc.getSoundEnabled(), isFalse);
    await _svc.setSoundEnabled(enabled: true);
    expect(await _svc.getSoundEnabled(), isTrue);
  });

  test('the choice rides the settings export (and so the backup)', () async {
    await _svc.setSoundEnabled(enabled: false);
    final export = await _svc.exportData();
    final rows = (export['settings'] as List).cast<Map<String, Object?>>();
    final row = rows.firstWhere((r) => r['key'] == 'sound_enabled');
    expect(row['value'], 'false');
  });
}
