// textgate guard, widget states the screen-level guard does not reach:
// every sync-card state, every PC poke outcome, the settings sheet in each
// progression mode, and the GitHub mirror screen.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise_state.dart';
import 'package:workout_app/models/progression.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/github_mirror_screen.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';
import 'package:workout_app/widgets/pc_poke_line.dart';
import 'package:workout_app/widgets/sync_setup_banner.dart';
import 'package:workout_app/widgets/sync_status_card.dart';

import 'fake_secure_storage.dart';
import 'text_free_guard.dart';

Widget _app(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

void main() {
  const statuses = [
    SyncStatus(state: SyncState.notConnected),
    SyncStatus(state: SyncState.failed, reason: 'sync failed: offline'),
    SyncStatus(state: SyncState.outOfDate, age: Duration(hours: 30)),
    SyncStatus(state: SyncState.synced, age: Duration(minutes: 5)),
  ];
  for (final s in statuses) {
    testWidgets('sync card: ${s.state.name}', (tester) async {
      await tester.pumpWidget(
        _app(SyncStatusCard(status: s, onRetry: () {}, onSetUp: () {})),
      );
      expectTextFree(tester);
    });
  }

  testWidgets('sync setup banner', (tester) async {
    await tester.pumpWidget(_app(const SyncSetupBanner()));
    expectTextFree(tester);
  });

  const pokes = [
    PokeResult(
      outcome: PokeOutcome.credited,
      reason: 'credited',
      shutdown: '22:00',
      gamingBudgetMinutes: 90,
    ),
    PokeResult(outcome: PokeOutcome.duplicate, reason: 'dup'),
    PokeResult(outcome: PokeOutcome.sandbox, reason: 'sb', roundTripMs: 40),
    PokeResult(outcome: PokeOutcome.alreadyPaidToday, reason: 'paid'),
    PokeResult(outcome: PokeOutcome.notCounted, reason: 'too short'),
    PokeResult.failed('no reply'),
  ];
  for (final p in pokes) {
    testWidgets('pc poke line: ${p.outcome.name}', (tester) async {
      await tester.pumpWidget(_app(PcPokeLine(poke: Future.value(p))));
      await tester.pump();
      expectTextFree(tester);
    });
  }

  for (final mode in ProgressionMode.values) {
    testWidgets('settings sheet: ${mode.name}', (tester) async {
      final state = ExerciseState.initial(workoutA.first).copyWith(mode: mode);
      await tester.pumpWidget(
        _app(
          ExerciseSettingsSheet(
            state: state,
            onChanged: (_) {},
            onDeload: () async => null,
          ),
        ),
      );
      expectTextFree(tester);
    });
  }

  group('github mirror screen', () {
    setUpAll(() {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    });

    setUp(() async {
      StorageService.resetForTesting();
      await StorageService.init();
      installFakeSecureStorage();
    });

    testWidgets('idle', (tester) async {
      await tester.runAsync(() async {
        await tester.pumpWidget(
          MaterialApp(theme: buildAppTheme(), home: const GitHubMirrorScreen()),
        );
        await Future<void>.delayed(const Duration(milliseconds: 300));
      });
      await tester.pump();
      expectTextFree(tester);
    });
  });
}
