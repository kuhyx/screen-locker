/// Monthly calendar showing which days had workouts.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Monthly calendar widget that highlights days with completed workouts.
class WorkoutCalendar extends StatelessWidget {
  /// Creates a [WorkoutCalendar].
  const WorkoutCalendar({
    required this.workoutDates,
    required this.month,
    required this.onPrevMonth,
    required this.onNextMonth,
    super.key,
  });

  /// Set of YYYY-MM-DD date strings that had at least one workout.
  final Set<String> workoutDates;

  /// Only the year and month of this DateTime are used.
  final DateTime month;

  /// Called when the user taps the previous-month chevron.
  final VoidCallback onPrevMonth;

  /// Called when the user taps the next-month chevron.
  final VoidCallback onNextMonth;

  static const _weekHeaders = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

  static const _monthNames = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  String _dateKey(int year, int m, int day) =>
      '$year-${m.toString().padLeft(2, '0')}-${day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final year = month.year;
    final m = month.month;
    final daysInMonth = DateTime(year, m + 1, 0).day;
    // weekday: 1=Mon..7=Sun → offset 0..6
    final firstWeekday = DateTime(year, m).weekday - 1;
    final totalCells = firstWeekday + daysInMonth;
    final rows = (totalCells / 7).ceil();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Column(
        children: [
          // Month navigation header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                icon: Icon(
                  Icons.chevron_left,
                  color: colorScheme.onSurfaceVariant,
                ),
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                onPressed: onPrevMonth,
              ),
              Text(
                '${_monthNames[m - 1]} $year',
                style: TextStyle(
                  color: colorScheme.onSurface,
                  fontWeight: FontWeight.bold,
                  fontSize: AppTextSize.label,
                ),
              ),
              IconButton(
                icon: Icon(
                  Icons.chevron_right,
                  color: colorScheme.onSurfaceVariant,
                ),
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                onPressed: onNextMonth,
              ),
            ],
          ),
          const SizedBox(height: 6),
          // Day-of-week headers
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: _weekHeaders
                .map(
                  (h) => SizedBox(
                    width: 30,
                    child: Text(
                      h,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: colorScheme.onSurfaceVariant,
                        fontSize: AppTextSize.caption,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 4),
          // Day grid
          ...List.generate(rows, (row) {
            return Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: List.generate(7, (col) {
                final cell = row * 7 + col;
                final day = cell - firstWeekday + 1;
                if (day < 1 || day > daysInMonth) {
                  return const SizedBox(width: 30, height: 30);
                }
                final key = _dateKey(year, m, day);
                final worked = workoutDates.contains(key);
                return Container(
                  width: 30,
                  height: 30,
                  margin: const EdgeInsets.symmetric(vertical: 2),
                  decoration: worked
                      ? BoxDecoration(
                          shape: BoxShape.circle,
                          color: status.success,
                        )
                      : null,
                  alignment: Alignment.center,
                  child: Text(
                    '$day',
                    style: TextStyle(
                      // on-fill (dark) on the success circle, muted otherwise.
                      color: worked
                          ? colorScheme.onPrimary
                          : colorScheme.onSurfaceVariant,
                      fontSize: AppTextSize.caption,
                      fontWeight: worked ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                );
              }),
            );
          }),
        ],
      ),
    );
  }
}
