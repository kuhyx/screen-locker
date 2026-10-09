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

  Color? colorOf(WidgetTester tester) =>
      tester.widget<Text>(find.byKey(const Key('pc-poke-result'))).style!.color;

  testWidgets('pending shows "applying" with a spinner', (tester) async {
    final never = Completer<PokeResult>();
    await show(tester, never.future);
    expect(find.byKey(const Key('pc-poke-pending')), findsOneWidget);
    expect(find.text('PC: applying…'), findsOneWidget);
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
    expect(find.text('PC ✓ (sandbox, not credited) · 77 ms'), findsOneWidget);
    expect(colorOf(tester), status.success);
  });

  testWidgets('a duplicate is neutral', (tester) async {
    await show(
      tester,
      Future.value(
        const PokeResult(outcome: PokeOutcome.duplicate, reason: 'dup'),
      ),
    );
    expect(find.text('PC: already credited'), findsOneWidget);
    expect(colorOf(tester), theme.colorScheme.onSurfaceVariant);
  });

  testWidgets('a failure is a warning naming the sync fallback', (
    tester,
  ) async {
    await show(tester, Future.value(const PokeResult.failed('timed out')));
    expect(find.text('PC: will credit within 60 s (via sync)'), findsOneWidget);
    expect(colorOf(tester), status.warning);
  });
}
