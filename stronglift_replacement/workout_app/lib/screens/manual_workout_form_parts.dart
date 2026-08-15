// The small, stateless pieces of the manual-workout form.
//
// A `part` so the extension keeps reaching `_fields` and `context`. All three
// are setState-free — `setState` is `@protected` and unreachable from an
// extension — so the interactive controls (the sport dropdown and the RPE
// slider) stay on the state class.
part of 'manual_workout_screen.dart';

/// The form's non-interactive building blocks.
extension _ManualWorkoutFormParts on _ManualWorkoutScreenState {
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

  /// Reads [key]'s field as an int, treating blank or unparsable as 0.
  int _int(String key) => int.tryParse(_fields[key]!.text.trim()) ?? 0;

  /// Reads [key]'s field verbatim.
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
}
