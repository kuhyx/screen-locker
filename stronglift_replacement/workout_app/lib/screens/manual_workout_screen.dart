/// Form for logging a manual (off-app) workout that syncs to the PC.
///
/// Mirrors the PC screen-locker manual-workout form: the same fields, the same
/// validation ([validateManualWorkout]), and the same rolling budget
/// (2/week, 5/month) computed over the merged cross-device record set. On
/// submit it builds the shared sync payload and pushes it to the phone's device
/// log; the PC ingests it as a counted `manual_workout`.
///
/// The workout date defaults to today and may be set up to
/// [kManualWorkoutMaxDaysAhead] days ahead (never back): a planned session is
/// logged now and credited by the PC on its own date. The budget is read as
/// of the chosen date, so moving the date re-evaluates it.
library;

import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/done_today.dart';
import 'package:workout_app/services/sync_device_id.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';

part 'manual_workout_actions.dart';
part 'manual_workout_form_parts.dart';

/// How many days ahead a manual workout may be dated. Past dates are never
/// offered: a manual entry is either today's or a planned one.
const int kManualWorkoutMaxDaysAhead = 7;

/// A screen that logs an off-app workout and syncs it to the PC.
class ManualWorkoutScreen extends StatefulWidget {
  /// Creates the manual-workout form. [syncService]/[clock] are injectable for
  /// tests; production uses a real [WorkoutSyncService] and [DateTime.now].
  const ManualWorkoutScreen({super.key, this.syncService, this.clock});

  /// Sync service used to read the budget and push the workout.
  final WorkoutSyncService? syncService;

  /// Returns "now"; defaults to [DateTime.now].
  final DateTime Function()? clock;

  @override
  State<ManualWorkoutScreen> createState() => _ManualWorkoutScreenState();
}

class _ManualWorkoutScreenState extends State<ManualWorkoutScreen> {
  late final WorkoutSyncService _sync =
      widget.syncService ?? WorkoutSyncService();
  DateTime Function() get _clock => widget.clock ?? DateTime.now;

  final _fields = <String, TextEditingController>{
    for (final key in [
      'start_time',
      'end_time',
      'location_name',
      'transport_method',
      'cost',
      'reservation_phone',
      'techniques_practiced',
      'warm_up_minutes',
      'pain_or_injury',
      'matches_won',
      'matches_lost',
      'sets_won',
      'sets_lost',
      'racket',
      'balls',
      'activity_type_other',
      'activity_details',
      'equipment',
      'went_well',
      'to_improve',
      'overall_feeling',
    ])
      key: TextEditingController(),
  };

  String _sport = kSportTableTennis;
  double _rpe = 5;
  String? _error;
  bool _submitting = false;
  List<Map<String, dynamic>> _payloads = const [];
  Set<String> _tombstoned = const {};
  bool _budgetLoaded = false;

  /// The workout date (a calendar day, no time). Starts as today.
  late DateTime _date = _today();

  DateTime _today() {
    final now = _clock();
    return DateTime(now.year, now.month, now.day);
  }

  /// Read fresh on every build, so a date change re-evaluates it without
  /// another round trip to the sync backend.
  ManualBudget get _budget => countManualBudget(_payloads, _date);

  @override
  void initState() {
    super.initState();
    unawaited(_loadBudget());
  }

  @override
  void dispose() {
    for (final c in _fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// Runs [fn] inside `setState` on behalf of this library's extensions,
  /// which cannot call the `@protected` original.
  void _applyState(VoidCallback fn) => setState(fn);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final budget = _budget;
    final exhausted = budget.exhausted;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        // textgate: was "Log Manual Workout".
        title: Icon(
          Icons.edit_note,
          color: colorScheme.onSurface,
          semanticLabel: 'Log Manual Workout',
        ),
      ),
      body: !_budgetLoaded
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // Above the exhausted branch on purpose: a full window around
                // today must not stop the user picking a free day later on.
                _dateRow(),
                _budgetBanner(budget),
                if (exhausted)
                  // textgate: was "Manual-workout budget exhausted for a
                  // window containing <date> — pick another date."
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Icon(
                      Icons.block,
                      key: const Key('mw_exhausted'),
                      size: 40,
                      color: colorScheme.error,
                      semanticLabel:
                          'Manual-workout budget exhausted — '
                          'pick another date.',
                    ),
                  )
                else ...[
                  _section(),
                  _sportDropdown(),
                  ..._basicFields(),
                  _section(),
                  ..._logisticsFields(),
                  _section(),
                  ..._sportFields(),
                  _rpeSlider(),
                  ..._detailFields(),
                  _section(),
                  ..._reflectionFields(),
                  if (_error != null)
                    // textgate: the refusal reason is spoken only; painted
                    // as an error glyph.
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Icon(
                        Icons.error_outline,
                        key: const Key('mw_error'),
                        color: colorScheme.error,
                        semanticLabel: _error,
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: ElevatedButton(
                      onPressed: _submitting ? null : _submit,
                      child: const Icon(Icons.save, semanticLabel: 'SUBMIT'),
                    ),
                  ),
                ],
              ],
            ),
    );
  }

  Widget _sportDropdown() => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: DropdownButton<String>(
      value: _sport,
      dropdownColor: Theme.of(context).colorScheme.surfaceContainerHigh,
      style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
      isExpanded: true,
      items: [
        // textgate: sport glyphs; the names are spoken only.
        for (final entry in kSportLabels.entries)
          DropdownMenuItem(
            value: entry.key,
            child: Icon(
              entry.key == kSportTableTennis
                  ? Icons.sports_tennis
                  : Icons.sports,
              semanticLabel: entry.value,
            ),
          ),
      ],
      onChanged: (value) {
        if (value != null) setState(() => _sport = value);
      },
    ),
  );

  Widget _rpeSlider() => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        // textgate: was "RPE 5"; an effort glyph and the number.
        Icon(
          Icons.speed,
          color: Theme.of(context).colorScheme.onSurface,
          semanticLabel: 'RPE',
        ),
        const SizedBox(width: 4),
        Text(
          '${_rpe.round()}',
          key: const Key('mw_rpe'),
          style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
        ),
        Expanded(
          child: Slider(
            value: _rpe,
            min: kManualWorkoutRpeMin.toDouble(),
            max: kManualWorkoutRpeMax.toDouble(),
            divisions: kManualWorkoutRpeMax - kManualWorkoutRpeMin,
            label: '${_rpe.round()}',
            onChanged: (value) => setState(() => _rpe = value),
          ),
        ),
      ],
    ),
  );
}
