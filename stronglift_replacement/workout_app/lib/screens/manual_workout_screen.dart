/// Form for logging a manual (off-app) workout that syncs to the PC.
///
/// Mirrors the PC screen-locker manual-workout form: the same fields, the same
/// validation ([validateManualWorkout]), and the same rolling budget
/// (2/week, 5/month) computed over the merged cross-device record set. On
/// submit it builds the shared sync payload and pushes it to the phone's device
/// log; the PC ingests it as a counted `manual_workout`.
library;

import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:workout_app/models/manual_workout.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';

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
  ManualBudget? _budget;
  bool _budgetLoaded = false;

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

  Future<void> _loadBudget() async {
    final payloads = await _sync.readMergedManualPayloads();
    if (!mounted) return;
    setState(() {
      _budget = countManualBudget(payloads, _clock());
      _budgetLoaded = true;
    });
  }

  int _int(String key) => int.tryParse(_fields[key]!.text.trim()) ?? 0;
  String _str(String key) => _fields[key]!.text;

  ManualWorkoutDraft _draft() => ManualWorkoutDraft(
    sport: _sport,
    startTime: _str('start_time'),
    endTime: _str('end_time'),
    locationName: _str('location_name'),
    transportMethod: _str('transport_method'),
    cost: _str('cost'),
    rpe: _rpe.round(),
    wentWell: _str('went_well'),
    toImprove: _str('to_improve'),
    overallFeeling: _str('overall_feeling'),
    reservationPhone: _str('reservation_phone'),
    techniquesPracticed: _str('techniques_practiced'),
    warmUpMinutes: _str('warm_up_minutes'),
    painOrInjury: _str('pain_or_injury').trim().isEmpty
        ? 'none'
        : _str('pain_or_injury'),
    matchesWon: _int('matches_won'),
    matchesLost: _int('matches_lost'),
    setsWon: _int('sets_won'),
    setsLost: _int('sets_lost'),
    racket: _str('racket'),
    balls: _str('balls'),
    activityTypeOther: _str('activity_type_other'),
    activityDetails: _str('activity_details'),
    equipment: _str('equipment'),
  );

  Future<void> _submit() async {
    final draft = _draft();
    final error = validateManualWorkout(draft);
    if (error != null) {
      setState(() => _error = error);
      return;
    }
    setState(() {
      _error = null;
      _submitting = true;
    });
    final now = _clock();
    final date =
        '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
    await _sync.pushManual(
      buildManualRecord(draft, date, hlc: Hlc.newTick('phone')),
    );
    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final budget = _budget;
    final exhausted = budget?.exhausted ?? false;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colorScheme.surfaceContainerHigh,
        title: Text(
          'Log Manual Workout',
          style: TextStyle(color: colorScheme.onSurface),
        ),
      ),
      body: !_budgetLoaded
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _budgetBanner(budget!),
                if (exhausted)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      'Manual-workout budget exhausted for this window.',
                      style: TextStyle(color: colorScheme.error),
                    ),
                  )
                else ...[
                  _section('Basics'),
                  _sportDropdown(),
                  _text('start_time', 'Start time (HH:MM)'),
                  _text('end_time', 'End time (HH:MM)'),
                  _section('Location & logistics'),
                  _text('location_name', 'Location name'),
                  _text('transport_method', 'How did you get there?'),
                  _text('cost', 'Cost (e.g. 40 PLN)'),
                  _text('reservation_phone', 'Reservation phone (optional)'),
                  _section('Activity details'),
                  ..._sportFields(),
                  _rpeSlider(),
                  _text('techniques_practiced', 'Techniques (optional)'),
                  _text('warm_up_minutes', 'Warm-up (optional)'),
                  _text('pain_or_injury', 'Pain or injury (optional)'),
                  _section('Reflection'),
                  _text('went_well', 'What went well', lines: 3),
                  _text('to_improve', 'What to improve', lines: 3),
                  _text('overall_feeling', 'Overall feeling', lines: 3),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Text(
                        _error!,
                        style: TextStyle(color: colorScheme.error),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: ElevatedButton(
                      onPressed: _submitting ? null : _submit,
                      child: const Text('SUBMIT'),
                    ),
                  ),
                ],
              ],
            ),
    );
  }

  List<Widget> _sportFields() {
    if (_sport == kSportTableTennis) {
      return [
        _text('matches_won', 'Matches won'),
        _text('matches_lost', 'Matches lost'),
        _text('sets_won', 'Sets won'),
        _text('sets_lost', 'Sets lost'),
        _text('racket', 'Racket used'),
        _text('balls', 'Balls used'),
      ];
    }
    return [
      _text('activity_type_other', 'What sport/activity'),
      _text('activity_details', 'What was done', lines: 3),
      _text('equipment', 'Equipment (optional)'),
    ];
  }

  Widget _budgetBanner(ManualBudget budget) => Text(
    'Manual: ${budget.week}/$kManualWorkoutBudgetPer7Days this week · '
    '${budget.month}/$kManualWorkoutBudgetPer30Days this month',
    style: TextStyle(
      color: Theme.of(context).colorScheme.primary,
      fontSize: AppTextSize.body,
    ),
  );

  Widget _section(String title) => Padding(
    padding: const EdgeInsets.only(top: 16, bottom: 4),
    child: Text(
      title,
      style: TextStyle(
        color: Theme.of(context).colorScheme.primary,
        fontSize: AppTextSize.subtitle,
        fontWeight: FontWeight.bold,
      ),
    ),
  );

  Widget _sportDropdown() => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: DropdownButton<String>(
      value: _sport,
      dropdownColor: Theme.of(context).colorScheme.surfaceContainerHigh,
      style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
      isExpanded: true,
      items: [
        for (final entry in kSportLabels.entries)
          DropdownMenuItem(value: entry.key, child: Text(entry.value)),
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
        Text(
          'RPE ${_rpe.round()}',
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

  Widget _text(String key, String label, {int lines = 1}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: TextField(
      key: Key('mw_$key'),
      controller: _fields[key],
      maxLines: lines,
      style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
      // filled/fillColor/border inherit from the shared inputDecorationTheme
      // (theme.dart) — only the field-specific label needs setting here.
      decoration: InputDecoration(
        labelText: label,
        labelStyle: TextStyle(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    ),
  );
}
