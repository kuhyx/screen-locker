/// Icon-only export/import controls; the outcome shows as an icon, not text.
library;

import 'dart:developer' show log;

import 'package:flutter/material.dart';
import 'package:workout_app/services/data_transfer.dart';
import 'package:workout_app/services/storage_service.dart';

/// How the last export or import ended.
enum _Outcome { done, skipped, failed }

/// Export and import buttons plus a result icon.
class DataTransferButtons extends StatefulWidget {
  /// Creates the buttons; the seams default to the real platform flows.
  const DataTransferButtons({
    super.key,
    this.onImported,
    this.exporter = exportUserData,
    this.importer = importUserData,
  });

  /// Called after an import wrote rows, so the caller can reload.
  final VoidCallback? onImported;

  /// Writes the export; false when the user cancelled.
  final Future<bool> Function() exporter;

  /// Merges a picked export; null when cancelled, else what it did.
  final Future<ImportReport?> Function() importer;

  @override
  State<DataTransferButtons> createState() => _DataTransferButtonsState();
}

class _DataTransferButtonsState extends State<DataTransferButtons> {
  bool _busy = false;
  _Outcome? _outcome;

  Future<void> _run(String what, Future<_Outcome?> Function() action) async {
    setState(() {
      _busy = true;
      _outcome = null;
    });
    _Outcome? outcome;
    try {
      outcome = await action();
    } on Object catch (error, stackTrace) {
      log(
        'Data $what failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      debugPrint('WorkoutApp: data $what FAILED: $error');
      outcome = _Outcome.failed;
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _outcome = outcome;
    });
  }

  Future<_Outcome?> _export() async =>
      await widget.exporter() ? _Outcome.done : null;

  Future<_Outcome?> _import() async {
    final report = await widget.importer();
    if (report == null) return null;
    if (report.rows + report.manualRecords > 0) widget.onImported?.call();
    return report.manualSkipped ? _Outcome.skipped : _Outcome.done;
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        IconButton(
          onPressed: _busy ? null : () => _run('export', _export),
          icon: const Icon(Icons.save_alt, semanticLabel: 'Export data'),
        ),
        IconButton(
          onPressed: _busy ? null : () => _run('import', _import),
          icon: const Icon(Icons.file_open, semanticLabel: 'Import data'),
        ),
        if (_outcome == _Outcome.done)
          Icon(
            Icons.check_circle,
            color: colorScheme.primary,
            semanticLabel: 'Done',
          )
        else if (_outcome == _Outcome.skipped)
          Icon(
            Icons.warning_amber,
            color: colorScheme.tertiary,
            semanticLabel: 'Manual workouts skipped',
          )
        else if (_outcome == _Outcome.failed)
          Icon(
            Icons.error_outline,
            color: colorScheme.error,
            semanticLabel: 'Failed',
          ),
      ],
    );
  }
}
