// PcPokeLine: a spinner while the poke is in flight, then one coloured line.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/pc_poke_line.dart';

void main() {
  final theme = buildAppTheme();
  final status = theme.extension<AppStatusColors>()!;

  Future<void> show(WidgetTester tester, Future<PokeResult> poke) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: theme,
        home: Scaffold(body: PcPokeLine(poke: poke)),
      ),
    );
    await tester.pump();
  }

  // The outcome colour lives on the glyphs (textgate: no sentence painted).
  Color? colorOf(WidgetTester tester) => tester
      .widget<Icon>(
        find
            .descendant(
              of: find.byKey(const Key('pc-poke-result')),
              matching: find.byType(Icon),
            )
            .first,
      )
      .color;

  testWidgets('pending shows "applying" with a spinner', (tester) async {
    final never = Completer<PokeResult>();
    await show(tester, never.future);
    expect(find.byKey(const Key('pc-poke-pending')), findsOneWidget);
    expect(find.bySemanticsLabel('PC: applying…'), findsOneWidget);
    expect(find.byIcon(Icons.computer), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('a sandbox round trip is a success line with its time', (
    tester,
  ) async {
    await show(
      tester,
      Future.value(
        const PokeResult(
          outcome: PokeOutcome.sandbox,
          reason: 'sandbox',
          roundTripMs: 77,
        ),
      ),
    );
    expect(
      find.bySemanticsLabel('PC ✓ (sandbox, not credited) · 77 ms'),
      findsOneWidget,
    );
    expect(find.text(' 77'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(colorOf(tester), status.success);
  });

  testWidgets('a duplicate is neutral', (tester) async {
    await show(
      tester,
      Future.value(
        const PokeResult(outcome: PokeOutcome.duplicate, reason: 'dup'),
      ),
    );
    expect(find.bySemanticsLabel('PC: already credited'), findsOneWidget);
    expect(find.byIcon(Icons.done_all), findsOneWidget);
    expect(colorOf(tester), theme.colorScheme.onSurfaceVariant);
  });

  testWidgets('a failure is a warning naming the sync fallback', (
    tester,
  ) async {
    await show(tester, Future.value(const PokeResult.failed('timed out')));
    expect(
      find.bySemanticsLabel('PC: will credit within 60 s (via sync)'),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.schedule), findsOneWidget);
    expect(colorOf(tester), status.warning);
  });

  testWidgets('a credit shows the new shutdown and gaming hours', (
    tester,
  ) async {
    await show(
      tester,
      Future.value(
        const PokeResult(
          outcome: PokeOutcome.credited,
          reason: 'credited',
          shutdown: '22:00',
          gamingBudgetMinutes: 90,
        ),
      ),
    );
    expect(find.text(' 22:00'), findsOneWidget);
    expect(find.text(' 1.5h'), findsOneWidget);
    expect(find.byIcon(Icons.power_settings_new), findsOneWidget);
    expect(colorOf(tester), status.success);
  });

  testWidgets('not counted is a warning block glyph', (tester) async {
    await show(
      tester,
      Future.value(
        const PokeResult(outcome: PokeOutcome.notCounted, reason: 'short'),
      ),
    );
    expect(find.byIcon(Icons.block), findsOneWidget);
    expect(colorOf(tester), status.warning);
  });
}
