/// Monthly calendar showing which days had workouts.
library;

import 'package:flutter/material.dart';

class WorkoutCalendar extends StatelessWidget {
  const WorkoutCalendar({
    super.key,
    required this.workoutDates,
    required this.month,
    required this.onPrevMonth,
    required this.onNextMonth,
  });

  final Set<String> workoutDates;

  /// Only the year and month of this DateTime are used.
  final DateTime month;
  final VoidCallback onPrevMonth;
  final VoidCallback onNextMonth;

  static const _weekHeaders = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

  static const _monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  String _dateKey(int year, int m, int day) =>
      '$year-${m.toString().padLeft(2, '0')}-${day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final year = month.year;
    final m = month.month;
    final daysInMonth = DateTime(year, m + 1, 0).day;
    // weekday: 1=Mon..7=Sun → offset 0..6
    final firstWeekday = DateTime(year, m, 1).weekday - 1;
    final totalCells = firstWeekday + daysInMonth;
    final rows = (totalCells / 7).ceil();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          // Month navigation header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left, color: Colors.white70),
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                onPressed: onPrevMonth,
              ),
              Text(
                '${_monthNames[m - 1]} $year',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right, color: Colors.white70),
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
                      style: const TextStyle(
                        color: Colors.white38,
                        fontSize: 11,
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
                          color: Colors.green.shade700,
                        )
                      : null,
                  alignment: Alignment.center,
                  child: Text(
                    '$day',
                    style: TextStyle(
                      color: worked ? Colors.white : Colors.white38,
                      fontSize: 12,
                      fontWeight:
                          worked ? FontWeight.bold : FontWeight.normal,
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
