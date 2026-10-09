/// Bottom sheet for one exercise's progression mode, rep range, warmup,
/// streak thresholds, rest lengths, injury pause and manual deload — opened
/// from the mode chip on its workout tile and from the Settings screen.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/ui/theme.dart';

part 'exercise_settings_sheet_deload.dart';
part 'exercise_settings_sheet_rest.dart';
part 'exercise_settings_sheet_rows.dart';

/// Opens the settings sheet for [state]; [onChanged] runs on every edit.
///
/// [onDeload] runs after the user confirms "Deload now". It is separate
/// from [onChanged] because it moves weight and reps, which the settings
/// write path deliberately never touches; the host persists it and returns
/// the new state, or null when nothing changed.
///
/// Edits apply immediately rather than on a Save button: the sheet is a
/// quick mid-workout adjustment, and a dismissed sheet losing its changes
/// would be the surprising outcome.
Future<void> showExerciseSettingsSheet(
  BuildContext context, {
  required ExerciseState state,
  required ValueChanged<ExerciseState> onChanged,
  required Future<ExerciseState?> Function() onDeload,
}) => showModalBottomSheet<void>(
  context: context,
  // Taller than the default 9/16-of-the-screen cap once the rest rows are
  // in; the sheet sizes to its content and scrolls on a short screen.
  isScrollControlled: true,
  builder: (_) => ExerciseSettingsSheet(
    state: state,
    onChanged: onChanged,
    onDeload: onDeload,
  ),
);

/// Upper bound for the double-progression rep ceiling `n`.
const int _maxRepsHigh = 50;

/// Default injury-pause length.
const int kDefaultPauseDays = 14;

/// The sheet's contents. Public so tests can pump it without a route.
class ExerciseSettingsSheet extends StatefulWidget {
  /// Creates an [ExerciseSettingsSheet].
  const ExerciseSettingsSheet({
    required this.state,
    required this.onChanged,
    required this.onDeload,
    super.key,
  });

  /// The state being edited, as it was when the sheet opened.
  final ExerciseState state;

  /// Called with the updated state after every edit.
  final ValueChanged<ExerciseState> onChanged;

  /// Persists a manual deload; returns the new state, or null if none.
  final Future<ExerciseState?> Function() onDeload;

  @override
  State<ExerciseSettingsSheet> createState() => _ExerciseSettingsSheetState();
}

class _ExerciseSettingsSheetState extends State<ExerciseSettingsSheet> {
  late ExerciseState _s = widget.state;
  int _pauseDays = kDefaultPauseDays;

  void _update(ExerciseState next) {
    setState(() => _s = next);
    widget.onChanged(next);
  }

  /// Confirms, then deloads. The returned state replaces [_s] so a later
  /// edit in this same sheet does not hand the host a stale weight.
  Future<void> _deload() async {
    if (!await _confirmDeload(context, _s)) return;
    final next = await widget.onDeload();
    if (next == null || !mounted) return;
    setState(() => _s = next);
  }

  String get _modeHint => switch (_s.mode) {
    ProgressionMode.weight =>
      '+$kWeightIncrement kg per step; +1 rep once at the '
          '${_s.maxWeight} kg cap',
    ProgressionMode.reps => '+1 rep per step; the weight never changes',
    ProgressionMode.doubleProgression =>
      '+1 rep per step up to ${_s.repsHigh}, then +$kWeightIncrement kg '
          'and back to ${_s.repsLow}',
  };

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final caption = TextStyle(
      color: colorScheme.onSurfaceVariant,
      fontSize: AppTextSize.caption,
    );
    final isDouble = _s.mode == ProgressionMode.doubleProgression;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _s.name,
              style: TextStyle(
                color: colorScheme.onSurface,
                fontWeight: FontWeight.bold,
                fontSize: AppTextSize.body,
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<ProgressionMode>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(
                    value: ProgressionMode.weight,
                    label: Text('Weight'),
                  ),
                  ButtonSegment(
                    value: ProgressionMode.reps,
                    label: Text('Reps'),
                  ),
                  ButtonSegment(
                    value: ProgressionMode.doubleProgression,
                    label: Text('Reps→kg'),
                  ),
                ],
                selected: {_s.mode},
                onSelectionChanged: (m) => _update(_s.copyWith(mode: m.first)),
              ),
            ),
            const SizedBox(height: 8),
            // Fixed two-line box: the hint's length differs per mode, and a
            // sheet that changes height under the finger is the jump the
            // user asked never to see.
            SizedBox(
              height: 34,
              child: Text(_modeHint, style: caption, maxLines: 2),
            ),
            // Kept laid out in every mode for the same reason.
            Visibility(
              visible: isDouble,
              maintainSize: true,
              maintainAnimation: true,
              maintainState: true,
              child: _SettingRow(
                label: '+kg at',
                name: 'Top reps',
                value: _s.repsHigh,
                min: _s.repsLow + 1,
                max: _maxRepsHigh,
                suffix: 'reps, restart at',
                trailing: _Stepper(
                  name: 'Restart reps',
                  value: _s.repsLow,
                  min: 1,
                  max: _s.repsHigh - 1,
                  onChanged: (v) => _update(_s.copyWith(repsLow: v)),
                ),
                onChanged: (v) => _update(_s.copyWith(repsHigh: v)),
              ),
            ),
            const SizedBox(height: 4),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Warmup set'),
              value: _s.hasWarmup,
              onChanged: (v) => _update(_s.copyWith(hasWarmup: v)),
            ),
            _SettingRow(
              label: '↑ after',
              name: 'Wins needed',
              value: _s.successThreshold,
              min: 1,
              max: 5,
              suffix: 'wins,  ↓ after',
              trailing: _Stepper(
                name: 'Fails allowed',
                value: _s.failThreshold,
                min: 1,
                max: 5,
                onChanged: (v) => _update(_s.copyWith(failThreshold: v)),
              ),
              onChanged: (v) => _update(_s.copyWith(successThreshold: v)),
            ),
            const SizedBox(height: 8),
            _RestRows(state: _s, onChanged: _update),
            const SizedBox(height: 8),
            _PauseRow(
              pausedUntil: _s.isPausedAt(DateTime.now())
                  ? _s.pausedUntil
                  : null,
              days: _pauseDays,
              onDaysChanged: (v) => setState(() => _pauseDays = v),
              onPause: () => _update(
                _s.copyWith(pausedUntil: pauseEnd(DateTime.now(), _pauseDays)),
              ),
              onResume: () => _update(_s.copyWith(resume: true)),
            ),
            _DeloadRow(state: _s, onDeload: () => unawaited(_deload())),
          ],
        ),
      ),
    );
  }
}
