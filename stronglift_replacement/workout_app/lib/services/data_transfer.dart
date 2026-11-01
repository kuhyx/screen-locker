import 'dart:convert';

import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:workout_app/services/storage_service.dart';

/// Parses [source] and merges it; throws [FormatException] on a bad file.
Future<ImportReport> importExportText(String source) async {
  final decoded = jsonDecode(source);
  if (decoded is! Map<String, dynamic>) {
    throw const FormatException('export is not a JSON object');
  }
  return await StorageService.instance.importDataReport(decoded);
}

// coverage:ignore-start

String _exportFileName(DateTime now) =>
    'workout_app-export-${now.toIso8601String().substring(0, 10)}.json';

/// Saves an export via the system Save-as picker; false when cancelled.
Future<bool> exportUserData() async {
  final json = const JsonEncoder.withIndent(
    '  ',
  ).convert(await StorageService.instance.exportData());
  return await exportJsonText(
    fileName: _exportFileName(DateTime.now()),
    text: json,
  );
}

/// Picks an export and merges it; null when cancelled.
Future<ImportReport?> importUserData() async {
  final text = await pickJsonText();
  if (text == null) return null;
  return await importExportText(text);
}
// coverage:ignore-end
