import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/data_transfer.dart';
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

  test('importExportText merges a valid export and reports it', () async {
    final report = await importExportText(
      '{"format":"$kExportFormat","version":2,"settings":[]}',
    );
    expect(report.rows, 0);
    expect(report.manualSkipped, false);
  });

  test('a JSON array is rejected with a FormatException', () async {
    await expectLater(
      importExportText('[1, 2]'),
      throwsA(isA<FormatException>()),
    );
  });

  test('text that is not JSON is rejected with a FormatException', () async {
    await expectLater(
      importExportText('not json'),
      throwsA(isA<FormatException>()),
    );
  });
}
