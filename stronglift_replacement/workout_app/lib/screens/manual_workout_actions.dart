// What the manual-workout form DOES: load the ledger, pick a date, submit.
//
// A `part` so the extension keeps reaching the private state; it mutates it
// through the `_applyState` shim because `setState` is `@protected` and
// cannot be called from an extension (same pattern as home_screen_sync.dart).
part of 'manual_workout_screen.dart';

/// Loading, date selection and submission for the manual-workout form.
extension _ManualWorkoutActions on _ManualWorkoutScreenState {
  Future<void> _loadBudget() async {
    final ledger = await _sync.readManualLedger();
    if (!mounted) return;
    _applyState(() {
      _payloads = ledger.payloads;
      _tombstoned = ledger.tombstoned;
      _budgetLoaded = true;
    });
  }

  Future<void> _pickDate() async {
    final today = _today();
    final picked = await showDatePicker(
      context: context,
      // Clamped: a form left open across midnight holds yesterday, and the
      // picker asserts its initial date is inside the range.
      initialDate: _date.isBefore(today) ? today : _date,
      firstDate: today,
      lastDate: today.add(const Duration(days: kManualWorkoutMaxDaysAhead)),
      helpText: 'Workout date',
    );
    if (picked == null || !mounted) return;
    SandboxLog.event('manual date picked', {'date': dayKey(picked)});
    _applyState(() {
      _date = DateTime(picked.year, picked.month, picked.day);
      _error = null;
    });
  }

  /// Why [_date] can no longer be submitted, or null when it can.
  ///
  /// Re-checked at submit because the clock moves: a form opened at 23:58
  /// with "today" selected is dated yesterday by the time it is sent.
  String? _dateError() {
    final today = _today();
    if (_date.isBefore(today)) {
      return 'The workout date ${dayKey(_date)} is in the past — pick '
          'today or a day ahead.';
    }
    final last = today.add(const Duration(days: kManualWorkoutMaxDaysAhead));
    if (_date.isAfter(last)) {
      return 'A workout can be planned at most $kManualWorkoutMaxDaysAhead '
          'days ahead.';
    }
    return null;
  }

  Future<void> _submit() async {
    final draft = _draft();
    final date = dayKey(_date);
    final recordId = manualSyncRecordId(date, draft.startTime);
    final error =
        validateManualWorkout(draft) ??
        _dateError() ??
        // A deleted record's id stays deleted forever (tombstones are
        // sticky), so re-logging the same date and start time would vanish
        // on every device. Refuse it here, where the user can still act.
        (_tombstoned.contains(recordId)
            ? 'A workout at ${draft.startTime.trim()} on $date was deleted '
                  'earlier and cannot be logged again — use a different '
                  'start time.'
            : null);
    if (error != null) {
      SandboxLog.event('manual submit refused', {'reason': error});
      _applyState(() => _error = error);
      return;
    }
    _applyState(() {
      _error = null;
      _submitting = true;
    });
    final result = await _sync.pushManual(
      buildManualRecord(draft, date, hlc: Hlc.newTick(currentSyncDeviceId)),
    );
    SandboxLog.event('manual submit', {
      'id': recordId,
      'pushed': result.pushed,
      'reason': result.reason,
    });
    if (!mounted) return;
    if (!result.pushed) {
      // Popping here used to report a workout that never left the phone as
      // logged. Stay on the filled form and say why, so it can be retried.
      _applyState(() {
        _submitting = false;
        _error = 'Not saved — ${result.reason}';
      });
      return;
    }
    Navigator.of(context).pop(true);
  }
}
