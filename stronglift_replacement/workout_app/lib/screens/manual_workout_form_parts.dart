// The small, stateless pieces of the manual-workout form.
//
// A `part` so the extension keeps reaching `_fields` and `context`. All three
// are setState-free — `setState` is `@protected` and unreachable from an
// extension — so the interactive controls (the sport dropdown and the RPE
// slider) stay on the state class.
part of 'manual_workout_screen.dart';

/// The form's non-interactive building blocks.
extension _ManualWorkoutFormParts on _ManualWorkoutScreenState {
  /// The budget as seen from the selected date: the fullest 7- and 30-day
  /// windows around it, planned entries included.
  ///
  /// textgate: was "Manual around DATE: 0/2 per 7 days · 0/10 per 30
  /// days"; now the counts with their window length in days.
  Widget _budgetBanner(ManualBudget budget) => Row(
    key: const Key('mw_budget'),
    children: [
      Icon(
        Icons.event_repeat,
        size: 18,
        color: Theme.of(context).colorScheme.primary,
        semanticLabel: 'Manual-workout budget',
      ),
      const SizedBox(width: AppSpacing.sm),
      Text(
        '${budget.week}/$kManualWorkoutBudgetPer7Days ⋅ 7d    '
        '${budget.month}/$kManualWorkoutBudgetPer30Days ⋅ 30d',
        style: TextStyle(
          color: Theme.of(context).colorScheme.primary,
          fontSize: AppTextSize.body,
        ),
      ),
    ],
  );

  /// `+0` for today, `+1` for tomorrow, `+N` (textgate: was "today" /
  /// "tomorrow" / "in N days").
  String _relativeDay() {
    // Rounded, not truncated: across a DST change two local midnights are
    // 23 or 25 hours apart.
    final days = (_date.difference(_today()).inHours / 24).round();
    return '+$days';
  }

  /// The workout date and the button that changes it.
  Widget _dateRow() => Padding(
    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
    child: Row(
      children: [
        Expanded(
          child: Text(
            // textgate: was "Workout date: DATE (today)".
            '${dayKey(_date)}  ${_relativeDay()}',
            key: const Key('mw_date'),
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurface,
              fontSize: AppTextSize.body,
            ),
          ),
        ),
        TextButton(
          key: const Key('mw_pick_date'),
          onPressed: _submitting ? null : _pickDate,
          child: const Icon(
            Icons.calendar_today,
            size: 20,
            semanticLabel: 'CHANGE DATE',
          ),
        ),
      ],
    ),
  );

  /// A divider between field groups (textgate: was a word heading such as
  /// "Basics" or "Reflection").
  Widget _section() => Padding(
    padding: const EdgeInsets.only(top: 12, bottom: 4),
    child: Divider(color: Theme.of(context).colorScheme.primary),
  );

  /// A field marked by [icon]; [semanticsLabel] (the old floating label) is
  /// spoken only. [hint] is a numeral-only placeholder.
  Widget _text(
    String key,
    IconData icon,
    String semanticsLabel, {
    int lines = 1,
    String? hint,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: TextField(
      key: Key('mw_$key'),
      controller: _fields[key],
      maxLines: lines,
      style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
      // filled/fillColor/border inherit from the shared inputDecorationTheme
      // (theme.dart) — only the field-specific label needs setting here.
      decoration: InputDecoration(
        hintText: hint,
        prefixIcon: Icon(
          icon,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
          semanticLabel: semanticsLabel,
        ),
      ),
    ),
  );

  List<Widget> _basicFields() => [
    _text(
      'start_time',
      Icons.play_circle_outline,
      'Start time (HH:MM)',
      hint: '--:--',
    ),
    _text(
      'end_time',
      Icons.stop_circle_outlined,
      'End time (HH:MM)',
      hint: '--:--',
    ),
  ];

  List<Widget> _logisticsFields() => [
    _text('location_name', Icons.place, 'Location name'),
    _text('transport_method', Icons.directions_bus, 'How did you get there?'),
    _text('cost', Icons.payments, 'Cost (e.g. 40 PLN)'),
    _text('reservation_phone', Icons.phone, 'Reservation phone (optional)'),
  ];

  List<Widget> _detailFields() => [
    _text('techniques_practiced', Icons.psychology, 'Techniques (optional)'),
    _text('warm_up_minutes', Icons.wb_sunny, 'Warm-up (optional)'),
    _text('pain_or_injury', Icons.healing, 'Pain or injury (optional)'),
  ];

  List<Widget> _reflectionFields() => [
    _text('went_well', Icons.thumb_up, 'What went well', lines: 3),
    _text('to_improve', Icons.trending_up, 'What to improve', lines: 3),
    _text('overall_feeling', Icons.mood, 'Overall feeling', lines: 3),
  ];

  List<Widget> _sportFields() {
    if (_sport == kSportTableTennis) {
      return [
        _text('matches_won', Icons.emoji_events, 'Matches won'),
        _text('matches_lost', Icons.emoji_events_outlined, 'Matches lost'),
        _text('sets_won', Icons.add_circle_outline, 'Sets won'),
        _text('sets_lost', Icons.remove_circle_outline, 'Sets lost'),
        _text('racket', Icons.sports_tennis, 'Racket used'),
        _text('balls', Icons.sports_baseball, 'Balls used'),
      ];
    }
    return [
      _text('activity_type_other', Icons.sports, 'What sport/activity'),
      _text('activity_details', Icons.notes, 'What was done', lines: 3),
      _text('equipment', Icons.backpack, 'Equipment (optional)'),
    ];
  }

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
