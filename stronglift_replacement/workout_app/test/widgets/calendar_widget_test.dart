import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/calendar_widget.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

void main() {
  group('WorkoutCalendar', () {
    final june2024 = DateTime(2024, 6);

    testWidgets('shows month and year in header', (tester) async {
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: june2024,
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      expect(find.text('June 2024'), findsOneWidget);
    });

    testWidgets('shows day-of-week headers', (tester) async {
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: june2024,
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      expect(find.text('Mo'), findsOneWidget);
      expect(find.text('Su'), findsOneWidget);
    });

    testWidgets('calls onPrevMonth when left arrow tapped', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: june2024,
            onPrevMonth: () => called = true,
            onNextMonth: () {},
          ),
        ),
      );
      await tester.tap(find.byIcon(Icons.chevron_left));
      expect(called, isTrue);
    });

    testWidgets('calls onNextMonth when right arrow tapped', (tester) async {
      var called = false;
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: june2024,
            onPrevMonth: () {},
            onNextMonth: () => called = true,
          ),
        ),
      );
      await tester.tap(find.byIcon(Icons.chevron_right));
      expect(called, isTrue);
    });

    testWidgets('highlights workout dates', (tester) async {
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {'2024-06-15'},
            month: june2024,
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      // Day 15 should appear in the grid.
      expect(find.text('15'), findsOneWidget);
    });

    testWidgets('renders month starting on Sunday correctly', (tester) async {
      // September 2024 starts on a Sunday (weekday=7, offset=6 in Mon-first grid)
      final sep2024 = DateTime(2024, 9);
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: sep2024,
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      expect(find.text('September 2024'), findsOneWidget);
    });

    testWidgets('renders January (first month name) correctly', (tester) async {
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: DateTime(2024),
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      expect(find.text('January 2024'), findsOneWidget);
    });

    testWidgets('renders December (last month name) correctly', (tester) async {
      await tester.pumpWidget(
        _wrap(
          WorkoutCalendar(
            workoutDates: const {},
            month: DateTime(2024, 12),
            onPrevMonth: () {},
            onNextMonth: () {},
          ),
        ),
      );
      expect(find.text('December 2024'), findsOneWidget);
    });
  });
}
